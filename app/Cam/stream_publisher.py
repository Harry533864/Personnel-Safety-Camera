import logging
import os
import shutil
import subprocess

import cv2


class StreamPublisher:
    _probe_cache = {}
    _encoder_probe = None

    def __init__(self, name, url):
        self.name = name
        self.url = url
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.last_pipeline = None
        self.last_error = None
        self.last_encoder = None

    @classmethod
    def _has_gst_element(cls, element):
        if element in cls._probe_cache:
            return cls._probe_cache[element]

        if shutil.which("gst-inspect-1.0") is None:
            cls._probe_cache[element] = False
            return False

        try:
            result = subprocess.run(
                ["gst-inspect-1.0", element],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=2,
            )
            available = result.returncode == 0
        except Exception:
            available = False

        cls._probe_cache[element] = available
        return available

    @classmethod
    def _select_encoder(cls):
        if cls._encoder_probe is not None:
            return cls._encoder_probe

        cls._encoder_probe = (
            "nvv4l2h264enc"
            if cls._has_gst_element("nvv4l2h264enc")
            and cls._has_gst_element("nvvidconv")
            else "x264enc"
        )
        return cls._encoder_probe

    @staticmethod
    def suggest_bitrate_kbps(w, h, fps):
        pixels = int(w) * int(h)

        if pixels >= 2560 * 1440:
            return 15000
        if pixels >= 1920 * 1080:
            return 12000
        if pixels >= 1280 * 720:
            return 8000
        return 4000

    @staticmethod
    def _x264_threads():
        raw = os.environ.get("STREAM_X264_THREADS", "0")
        try:
            return max(0, int(raw))
        except ValueError:
            return 0

    @staticmethod
    def _x264_sliced_threads():
        raw = os.environ.get("STREAM_X264_SLICED_THREADS", "0")
        return str(raw).strip().lower() not in {"0", "false", "no", "off"}

    def build_pipeline(self, current_w, current_h, current_fps):
        current_w = int(current_w)
        current_h = int(current_h)
        current_fps = max(1, int(current_fps))
        bitrate_kbps = self.suggest_bitrate_kbps(current_w, current_h, current_fps)
        encoder = self._select_encoder()
        x264_threads = self._x264_threads()
        x264_sliced_threads = str(self._x264_sliced_threads()).lower()

        base = (
            f"appsrc is-live=true block=false format=time do-timestamp=true "
            f"! video/x-raw,format=BGR,width={current_w},height={current_h},framerate={current_fps}/1 "
            f"! queue leaky=downstream max-size-buffers=2 "
        )

        if encoder == "nvv4l2h264enc":
            bitrate_bps = bitrate_kbps * 1000
            pipeline = (
                f"{base}"
                f"! videoconvert "
                f"! video/x-raw,format=I420 "
                f"! nvvidconv "
                f"! video/x-raw(memory:NVMM),format=NV12 "
                f"! nvv4l2h264enc "
                f"bitrate={bitrate_bps} "
                f"control-rate=1 "
                f"iframeinterval={current_fps} "
                f"insert-sps-pps=true "
                f"maxperf-enable=true "
                f"! h264parse config-interval=1 "
                f"! flvmux streamable=true "
                f"! rtmpsink location={self.url} sync=false async=false"
            )
        else:
            pipeline = (
                f"{base}"
                f"! videoconvert "
                f"! video/x-raw,format=I420 "
                f"! x264enc "
                f"bitrate={bitrate_kbps} "
                f"speed-preset=ultrafast "
                f"tune=zerolatency "
                f"key-int-max={current_fps} "
                f"bframes=0 "
                f"threads={x264_threads} "
                f"sliced-threads={x264_sliced_threads} "
                f"byte-stream=false "
                f"! h264parse config-interval=1 "
                f"! flvmux streamable=true "
                f"! rtmpsink location={self.url} sync=false async=false"
            )

        self.last_encoder = encoder
        self.last_pipeline = pipeline
        return pipeline

    def open_writer(self, current_w, current_h, current_fps):
        pipeline = self.build_pipeline(
            current_w=current_w,
            current_h=current_h,
            current_fps=current_fps,
        )

        self.logger.info("Opening GStreamer writer: %s", pipeline)
        writer = cv2.VideoWriter(
            pipeline,
            cv2.CAP_GSTREAMER,
            0,
            float(current_fps),
            (int(current_w), int(current_h)),
            True,
        )

        if not writer.isOpened():
            self.last_error = "GStreamer VideoWriter open failed"
            raise RuntimeError(
                f"[{self.name}] Unable to open GStreamer VideoWriter. "
                "Check x264enc / rtmpsink / flvmux / MediaMTX."
            )

        self.last_error = None
        self.logger.info(
            "GStreamer writer started: %sx%s@%s url=%s",
            current_w,
            current_h,
            current_fps,
            self.url,
        )
        return writer

    def close_writer(self, writer):
        if writer is None:
            return

        try:
            writer.release()
        except Exception:
            self.logger.exception("Failed to release GStreamer writer")
