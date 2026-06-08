import logging
import threading
import time
from pathlib import Path

from app.Cam.fps_meter import FpsMeter
from inference.python_tensorrt.model import Model


class InferenceWorker:
    def __init__(self, name, ai_config_path=None, enabled=False, on_detection=None):
        self.name = name
        self.ai_config_path = ai_config_path
        self.on_detection = on_detection
        self.logger = logging.getLogger(f"{__name__}.{name}")

        self._running = False
        self._thread = None

        self._enabled = bool(enabled)
        self._model = None
        self._ai_lock = threading.RLock()

        self._frame_lock = threading.Lock()
        self._latest_raw_frame = None
        self._latest_stream_frame = None
        self._latest_output_frame = None
        self._latest_output_time = 0.0

        self._status_lock = threading.Lock()
        self._last_raw_frame_at = 0.0
        self._last_success_at = 0.0
        self._last_latency_ms = None
        self._last_error = None
        self._frame_count = 0
        self._infer_fps = FpsMeter()
        self._next_model_retry_at = 0.0
        self._model_retry_interval = 10.0

    @property
    def enabled(self):
        with self._ai_lock:
            return self._enabled

    @property
    def model_loaded(self):
        with self._ai_lock:
            return self._model is not None

    def _format_time(self, timestamp):
        if not timestamp:
            return None
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(timestamp))

    def status(self):
        with self._frame_lock:
            has_raw_frame = self._latest_raw_frame is not None
            has_stream_frame = self._latest_stream_frame is not None
            has_output_frame = self._latest_output_frame is not None
            latest_output_time = self._latest_output_time

        with self._ai_lock:
            enabled = self._enabled
            model_loaded = self._model is not None

        with self._status_lock:
            return {
                "running": self._running,
                "thread_alive": bool(self._thread and self._thread.is_alive()),
                "enable_infer": enabled,
                "model_loaded": model_loaded,
                "has_raw_frame": has_raw_frame,
                "has_stream_frame": has_stream_frame,
                "has_infer_frame": has_output_frame,
                "latest_infer_frame_at": self._format_time(latest_output_time),
                "last_raw_frame_at": self._format_time(self._last_raw_frame_at),
                "last_infer_success_at": self._format_time(self._last_success_at),
                "last_infer_latency_ms": self._last_latency_ms,
                "last_infer_error": self._last_error,
                "frames_inferred": self._frame_count,
                "actual_infer_fps": self._infer_fps.fps(),
            }

    def put_frame(self, frame):
        if not self._running or frame is None:
            return False

        with self._frame_lock:
            self._latest_raw_frame = frame
            self._latest_stream_frame = frame

        with self._status_lock:
            self._last_raw_frame_at = time.time()

        return True

    def get_frame(self):
        with self._frame_lock:
            frame = self._latest_stream_frame

        if frame is None:
            return None

        with self._ai_lock:
            enable_infer = self._enabled
            model = self._model

        if not enable_infer or model is None:
            return frame

        try:
            rendered = model.try_render_latest(frame)
            return rendered if rendered is not None else frame
        except Exception:
            self.logger.exception("Failed to render latest AI overlay; streaming raw frame")
            return frame

    def get_frame_snapshot(self, include_overlay=True):
        with self._frame_lock:
            frame = self._latest_stream_frame

        with self._status_lock:
            frame_time = self._last_raw_frame_at

        if frame is None:
            return None, frame_time

        if not include_overlay:
            return frame, frame_time

        with self._ai_lock:
            enable_infer = self._enabled
            model = self._model

        if not enable_infer or model is None:
            return frame, frame_time

        try:
            rendered = model.try_render_latest(frame)
            return (rendered if rendered is not None else frame), frame_time
        except Exception:
            self.logger.exception("Failed to render latest AI overlay; streaming raw frame")
            return frame, frame_time

    def start(self):
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name=f"InferenceWorker-{self.name}",
        )
        self._thread.start()
        self.logger.info("Inference worker started")

    def stop(self):
        self._running = False

        if self._thread:
            self._thread.join()
            self._thread = None
            self.logger.info("Inference worker stopped")

        self.close_model()

    def set_enabled(
        self,
        enable,
        reload_when_enable=True,
        release_when_disable=True,
    ):
        enable = bool(enable)

        with self._ai_lock:
            old_enable = self._enabled
            self._enabled = enable

            if enable:
                self.logger.info("AI inference enable requested")
                try:
                    model = self._ensure_model_locked()

                    if reload_when_enable:
                        model.reload_config()
                        self.logger.info("AI config reloaded")

                    self.logger.info("AI inference enabled")
                except Exception as error:
                    self.logger.warning(
                        "AI model is not ready; raw video will keep streaming: %s",
                        error,
                    )
                    self._close_model_locked()
                    self._next_model_retry_at = time.time() + self._model_retry_interval
                    with self._status_lock:
                        self._last_error = str(error)
            else:
                self.logger.info("AI inference disable requested")

                if release_when_disable:
                    self._close_model_locked()
                    self.logger.info("AI inference disabled and model released")
                else:
                    self.logger.info("AI inference disabled; model kept loaded")

            if old_enable != enable:
                self.logger.info("AI inference state changed: %s -> %s", old_enable, enable)

    def reload_config(self):
        with self._ai_lock:
            if not self._enabled:
                self.logger.info("AI inference is disabled; skipping reload")
                return

            model = self._ensure_model_locked()
            model.reload_config()
            self.logger.info("AI config reloaded")

    def close_model(self):
        with self._ai_lock:
            self._close_model_locked()

    def _ensure_model_locked(self):
        if self._model is not None:
            return self._model

        if self.ai_config_path is None:
            raise RuntimeError(
                f"[{self.name}] enable_infer=True，但没有传入 ai_config_path"
            )

        config_path = Path(self.ai_config_path).resolve()

        if not config_path.exists():
            raise FileNotFoundError(f"[{self.name}] AIConfig.yaml 不存在: {config_path}")

        self.logger.info("Initializing AI model: %s", config_path)
        self._model = Model(config=str(config_path))
        self.logger.info("AI model initialized")
        return self._model

    def _close_model_locked(self):
        if self._model is None:
            return

        try:
            self._model.close()
        except Exception:
            self.logger.exception("Failed to close AI model")

        self._model = None

    def _run(self):
        while self._running:
            with self._frame_lock:
                frame = self._latest_raw_frame
                self._latest_raw_frame = None

            if frame is None:
                time.sleep(0.001)
                continue

            with self._ai_lock:
                enable_infer = self._enabled
                model = None
                if enable_infer:
                    now = time.time()
                    if now >= self._next_model_retry_at:
                        try:
                            model = self._ensure_model_locked()
                        except Exception as error:
                            self.logger.warning(
                                "AI model is not ready; streaming original frame: %s",
                                error,
                            )
                            self._close_model_locked()
                            self._next_model_retry_at = (
                                now + self._model_retry_interval
                            )
                            with self._status_lock:
                                self._last_error = str(error)

            if not enable_infer or model is None:
                result = frame
            else:
                try:
                    infer_start = time.perf_counter()
                    result = model.inference(frame)
                    infer_end = time.perf_counter()

                    if result is None:
                        result = frame

                    if getattr(model, "last_detection_flag", False) and self.on_detection:
                        try:
                            self.on_detection()
                        except Exception:
                            self.logger.exception("Detection callback failed")

                    with self._status_lock:
                        self._frame_count += 1
                        self._infer_fps.mark()
                        self._last_success_at = time.time()
                        self._last_latency_ms = round(
                            (infer_end - infer_start) * 1000,
                            2,
                        )
                        self._last_error = None

                except Exception as error:
                    self.logger.exception(
                        "AI inference failed; streaming original frame"
                    )
                    with self._status_lock:
                        self._last_error = str(error)
                    result = frame

            with self._frame_lock:
                self._latest_output_frame = result
                self._latest_output_time = time.time()

        self.logger.info("Inference worker exited")
