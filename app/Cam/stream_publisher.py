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
    def _encoder_candidates(cls):
        requested = str(os.environ.get("STREAM_ENCODER", "auto")).strip().lower()
        aliases = {
            "hardware": "nvv4l2h264enc",
            "hw": "nvv4l2h264enc",
            "openh264": "openh264enc",
            "x264": "x264enc",
        }
        requested = aliases.get(requested, requested)

        if requested != "auto":
            return [requested]

        if cls._encoder_probe is not None:
            return cls._encoder_probe

        candidates = []
        if cls._has_gst_element("nvv4l2h264enc") and cls._has_gst_element("nvvidconv"):
            candidates.append("nvv4l2h264enc")
        if cls._has_gst_element("x264enc"):
            candidates.append("x264enc")
        if cls._has_gst_element("openh264enc"):
            candidates.append("openh264enc")
        if not candidates:
            candidates.append("x264enc")
        cls._encoder_probe = candidates
        return candidates

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

    @staticmethod
    def _openh264_threads():
        raw = os.environ.get("STREAM_OPENH264_THREADS", "4")
        try:
            return max(0, int(raw))
        except ValueError:
            return 4

    def build_pipeline(self, current_w, current_h, current_fps, encoder=None):
        current_w = int(current_w)
        current_h = int(current_h)
        current_fps = max(1, int(current_fps))
        bitrate_kbps = self.suggest_bitrate_kbps(current_w, current_h, current_fps)
        encoder = encoder or self._encoder_candidates()[0]
        x264_threads = self._x264_threads()
        x264_sliced_threads = str(self._x264_sliced_threads()).lower()
        openh264_threads = self._openh264_threads()

        base = (
            f"appsrc is-live=true block=false format=time do-timestamp=true "
            f"! video/x-raw,format=BGR,width={current_w},height={current_h},framerate={current_fps}/1 "
            f"! queue leaky=downstream max-size-buffers=1 "
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
        elif encoder == "openh264enc":
            bitrate_bps = bitrate_kbps * 1000
            pipeline = (
                f"{base}"
                f"! videoconvert "
                f"! video/x-raw,format=I420 "
                f"! openh264enc "
                f"bitrate={bitrate_bps} "
                f"max-bitrate={bitrate_bps} "
                f"rate-control=bitrate "
                f"complexity=low "
                f"gop-size={current_fps} "
                f"multi-thread={openh264_threads} "
                f"slice-mode=auto "
                f"enable-frame-skip=false "
                f"background-detection=false "
                f"adaptive-quantization=false "
                f"scene-change-detection=false "
                f"deblocking=off "
                f"! video/x-h264,profile=baseline "
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
                f"vbv-buf-capacity=50 "
                f"rc-lookahead=0 "
                f"sync-lookahead=0 "
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
        errors = []
        for encoder in self._encoder_candidates():
            pipeline = self.build_pipeline(
                current_w=current_w,
                current_h=current_h,
                current_fps=current_fps,
                encoder=encoder,
            )

            self.logger.info("Opening GStreamer writer with %s: %s", encoder, pipeline)
            writer = cv2.VideoWriter(
                pipeline,
                cv2.CAP_GSTREAMER,
                0,
                float(current_fps),
                (int(current_w), int(current_h)),
                True,
            )

            if writer.isOpened():
                self.last_error = None
                self.last_encoder = encoder
                self.logger.info(
                    "GStreamer writer started: %sx%s@%s encoder=%s url=%s",
                    current_w,
                    current_h,
                    current_fps,
                    encoder,
                    self.url,
                )
                return writer

            writer.release()
            errors.append(f"{encoder}: open failed")
            self.logger.warning("GStreamer writer open failed with %s", encoder)

        self.last_error = "; ".join(errors) or "GStreamer VideoWriter open failed"
        raise RuntimeError(
            f"[{self.name}] Unable to open GStreamer VideoWriter. "
            f"Tried: {', '.join(self._encoder_candidates())}."
        )

    def close_writer(self, writer):
        if writer is None:
            return

        try:
            writer.release()
        except Exception:
            self.logger.exception("Failed to release GStreamer writer")
