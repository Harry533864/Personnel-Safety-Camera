import json
import logging
import shutil
import time
from pathlib import Path

import cv2

from app import time_sync
from app.Cam.stream_publisher import StreamPublisher
from app.utils import read_record_config


FFMPEG_RECORD_CANDIDATES = (
    ("mp4", "mp4v", "ffmpeg-mp4v"),
    ("avi", "MJPG", "ffmpeg-mjpg"),
)


class StreamRecorder:
    def __init__(
        self,
        name,
        ai_config_path,
        video_base_dir,
        enabled=False,
        bitrate_fn=None,
    ):
        self.name = name
        self.ai_config_path = ai_config_path
        self.video_base_dir = Path(video_base_dir).expanduser().resolve()
        self.enabled = bool(enabled)
        self.bitrate_fn = bitrate_fn or self._default_bitrate_kbps
        self.logger = logging.getLogger(f"{__name__}.{name}")

        self.writer = None
        self.start_time = 0.0
        self.start_epoch = 0.0
        self.duration_limit = 600.0
        self.need_restart = True
        self.cooldown_until = 0.0
        self.min_free_space_mb = 500
        self.file_path = None
        self.has_target = False
        self.frame_count = 0
        self.last_error = None
        self.last_encoder = None
        self._last_unavailable_reason = None

    @staticmethod
    def _default_bitrate_kbps(w, h, fps):
        pixels = int(w) * int(h)
        if pixels >= 2560 * 1440:
            return 15000
        if pixels >= 1920 * 1080:
            return 12000
        if pixels >= 1280 * 720:
            return 8000
        return 4000

    @property
    def writer_opened(self):
        return self.writer is not None and self.writer.isOpened()

    def mark_target(self):
        self.has_target = True

    def request_restart(self):
        self.need_restart = True

    def status(self):
        return {
            "enabled": self.enabled,
            "recording": self.writer_opened,
            "file": str(self.file_path) if self.file_path else None,
            "frames_recorded": self.frame_count,
            "cooldown_until": self._format_time(self.cooldown_until),
            "last_error": self.last_error,
            "encoder": self.last_encoder,
        }

    def _format_time(self, timestamp):
        if not timestamp:
            return None
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(timestamp))

    def _video_dir(self):
        video_dir = self.video_base_dir / "video" / self.name
        video_dir.mkdir(parents=True, exist_ok=True)
        return video_dir

    def _next_file_path(self, video_dir, timestamp_str, extension):
        file_path = video_dir / f"{timestamp_str}.{extension}"
        if not file_path.exists() and not file_path.with_suffix(".json").exists():
            return file_path

        index = 1
        while True:
            candidate = video_dir / f"{timestamp_str}_{index}.{extension}"
            if not candidate.exists() and not candidate.with_suffix(".json").exists():
                return candidate
            index += 1

    def _write_metadata(self):
        if self.file_path is None:
            return

        try:
            metadata_path = self.file_path.with_suffix(".json")
            metadata = {
                "filename": self.file_path.name,
                "title": self.file_path.stem,
                "target": self.name,
                "start_at": time_sync.format_local(self.start_epoch),
                "duration_sec": max(0, int(round(time.time() - self.start_time))),
                "has_target": bool(self.has_target),
                "time_synced": time_sync.is_synced(),
            }
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as error:
            self.last_error = str(error)
            self.logger.exception("Failed to write video metadata")

    def close(self, stream_stats=None):
        stream_stats = stream_stats or {}
        if self.writer is not None:
            try:
                self.writer.release()
                self.logger.info(
                    "Record segment ended: recorded=%s streamed=%s received=%s",
                    self.frame_count,
                    stream_stats.get("frames_written"),
                    stream_stats.get("frames_received"),
                )
            except Exception as error:
                self.last_error = str(error)
                self.logger.exception("Failed to release local record writer")

        self.writer = None
        self._write_metadata()
        self.file_path = None
        self.has_target = False
        self.frame_count = 0

    def maintain(self, current_w, current_h, current_fps, stream_stats=None):
        if not self.enabled:
            self.close(stream_stats)
            return

        now = time.time()
        if now < self.cooldown_until:
            return

        time_expired = (
            self.writer is not None
            and (now - self.start_time) >= self.duration_limit
        )

        if self.need_restart or self.writer is None or time_expired:
            self._open(current_w, current_h, current_fps, stream_stats)

    def _open_gstreamer_writer(self, video_dir, timestamp_str, width, height, fps):
        unavailable_reason = StreamPublisher.unavailable_reason()
        if unavailable_reason:
            if self._last_unavailable_reason != unavailable_reason:
                self.logger.warning(
                    "GStreamer recording unavailable: %s; trying file fallback",
                    unavailable_reason,
                )
                self._last_unavailable_reason = unavailable_reason
            else:
                self.logger.debug(
                    "GStreamer recording still unavailable: %s; trying file fallback",
                    unavailable_reason,
                )
            return None, None, None, unavailable_reason

        file_path = self._next_file_path(video_dir, timestamp_str, "mkv")
        bitrate = int(self.bitrate_fn(width, height, fps))
        encoder = StreamPublisher._select_encoder()

        base = (
            f"appsrc is-live=true block=false format=time do-timestamp=true "
            f"! video/x-raw,format=BGR,width={width},height={height},framerate={fps}/1 "
            f"! queue leaky=downstream max-size-buffers={fps} "
        )

        if encoder == "nvv4l2h264enc":
            gst_pipeline = (
                f"{base}"
                f"! videoconvert "
                f"! video/x-raw,format=I420 "
                f"! nvvidconv "
                f"! video/x-raw(memory:NVMM),format=NV12 "
                f"! nvv4l2h264enc "
                f"bitrate={bitrate * 1000} "
                f"control-rate=1 "
                f"iframeinterval={fps} "
                f"insert-sps-pps=true "
                f"maxperf-enable=true "
                f"! h264parse "
                f"! matroskamux "
                f"! filesink location={file_path} sync=false async=false"
            )
        else:
            gst_pipeline = (
                f"{base}"
                f"! videoconvert "
                f"! video/x-raw,format=I420 "
                f"! x264enc "
                f"bitrate={bitrate} "
                f"speed-preset=ultrafast "
                f"tune=zerolatency "
                f"bframes=0 "
                f"threads=2 "
                f"sliced-threads=true "
                f"! h264parse "
                f"! matroskamux "
                f"! filesink location={file_path} sync=false async=false"
            )

        writer = cv2.VideoWriter(
            gst_pipeline,
            cv2.CAP_GSTREAMER,
            0,
            float(fps),
            (width, height),
            True,
        )

        if writer.isOpened():
            return writer, file_path, encoder, None

        try:
            writer.release()
        except Exception:
            self.logger.exception("Failed to release unopened GStreamer record writer")
        return None, None, None, f"GStreamer record writer open failed: {file_path}"

    def _open_ffmpeg_writer(self, video_dir, timestamp_str, width, height, fps):
        errors = []
        api_preferences = []
        cap_ffmpeg = getattr(cv2, "CAP_FFMPEG", None)
        if cap_ffmpeg is not None:
            api_preferences.append((cap_ffmpeg, "CAP_FFMPEG"))
        api_preferences.append((0, "CAP_ANY"))

        for extension, fourcc_name, encoder_name in FFMPEG_RECORD_CANDIDATES:
            file_path = self._next_file_path(video_dir, timestamp_str, extension)
            fourcc = cv2.VideoWriter_fourcc(*fourcc_name)
            for api_preference, api_name in api_preferences:
                writer = cv2.VideoWriter(
                    str(file_path),
                    api_preference,
                    fourcc,
                    float(fps),
                    (width, height),
                    True,
                )
                if writer.isOpened():
                    return writer, file_path, f"{encoder_name}:{api_name}", None

                try:
                    writer.release()
                except Exception:
                    self.logger.exception("Failed to release unopened FFmpeg record writer")
                errors.append(f"{encoder_name}:{api_name} -> {file_path}")
                try:
                    if file_path.exists() and file_path.stat().st_size == 0:
                        file_path.unlink()
                except Exception:
                    self.logger.debug("Failed to remove empty record candidate", exc_info=True)

        return None, None, None, "FFmpeg file writer open failed: " + "; ".join(errors)

    def _open(self, current_w, current_h, current_fps, stream_stats=None):
        self.close(stream_stats)

        duration_min = read_record_config(self.ai_config_path)
        self.duration_limit = duration_min * 60.0

        video_dir = self._video_dir()
        total, used, free = shutil.disk_usage(str(video_dir))
        free_mb = free / (1024 * 1024)

        if free_mb < self.min_free_space_mb:
            self.last_error = f"low disk space: {free_mb:.2f}MB"
            self.logger.warning(
                "Disk space is low: %.2f MB free; recording paused for 60s",
                free_mb,
            )
            self.cooldown_until = time.time() + 60.0
            return

        width = int(current_w)
        height = int(current_h)
        fps = max(1, int(current_fps))
        start_epoch = time_sync.now_epoch()
        timestamp_str = time_sync.filename_timestamp(start_epoch)

        writer, file_path, encoder, gst_error = self._open_gstreamer_writer(
            video_dir, timestamp_str, width, height, fps
        )
        if writer is None:
            writer, file_path, encoder, ffmpeg_error = self._open_ffmpeg_writer(
                video_dir, timestamp_str, width, height, fps
            )
        else:
            ffmpeg_error = None

        if writer is None:
            error_parts = [part for part in (gst_error, ffmpeg_error) if part]
            self.last_error = "record writer open failed: " + " | ".join(error_parts)
            self.logger.warning(
                "Failed to open local record writer: %s; cooling down for 60s",
                self.last_error,
            )
            self.cooldown_until = time.time() + 60.0
            return

        self.writer = writer
        self.start_time = time.time()
        self.start_epoch = start_epoch
        self.file_path = file_path
        self.has_target = False
        self.need_restart = False
        self.last_error = None
        self.last_encoder = encoder
        self._last_unavailable_reason = None
        self.logger.info(
            "Record segment started: %s duration_min=%s",
            file_path,
            duration_min,
        )

    def write(self, frame, stream_stats=None):
        if not self.enabled or self.writer is None:
            return

        if time.time() < self.cooldown_until:
            return

        try:
            self.writer.write(frame)
            self.frame_count += 1
            self.last_error = None
        except Exception as error:
            self.last_error = str(error)
            self.logger.exception("Failed to write local video frame")
            self.close(stream_stats)
            self.cooldown_until = time.time() + 60.0
            self.need_restart = True
