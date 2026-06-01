import json
import logging
import shutil
import time
from pathlib import Path

import cv2

from app.Cam.stream_publisher import StreamPublisher
from app.utils import read_record_config


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
        self.duration_limit = 600.0
        self.need_restart = True
        self.cooldown_until = 0.0
        self.min_free_space_mb = 500
        self.file_path = None
        self.has_target = False
        self.frame_count = 0
        self.last_error = None
        self.last_encoder = None

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

    def _write_metadata(self):
        if self.file_path is None:
            return

        try:
            metadata_path = self.file_path.with_suffix(".json")
            metadata = {
                "filename": self.file_path.name,
                "title": self.file_path.stem,
                "target": self.name,
                "start_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%S",
                    time.localtime(self.start_time),
                ),
                "duration_sec": max(0, int(round(time.time() - self.start_time))),
                "has_target": bool(self.has_target),
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

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        file_path = video_dir / f"{timestamp_str}.mkv"
        bitrate = int(self.bitrate_fn(current_w, current_h, current_fps))
        encoder = StreamPublisher._select_encoder()

        base = (
            f"appsrc is-live=true block=false format=time do-timestamp=true "
            f"! video/x-raw,format=BGR,width={current_w},height={current_h},framerate={current_fps}/1 "
            f"! queue leaky=downstream max-size-buffers={current_fps} "
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
                f"iframeinterval={current_fps} "
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
            float(current_fps),
            (int(current_w), int(current_h)),
            True,
        )

        if not writer.isOpened():
            try:
                writer.release()
            except Exception:
                self.logger.exception("Failed to release unopened record writer")
            self.last_error = f"record writer open failed: {file_path}"
            self.logger.warning(
                "Failed to open local record writer: %s; cooling down for 60s",
                file_path,
            )
            self.cooldown_until = time.time() + 60.0
            return

        self.writer = writer
        self.start_time = time.time()
        self.file_path = file_path
        self.has_target = False
        self.need_restart = False
        self.last_error = None
        self.last_encoder = encoder
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
