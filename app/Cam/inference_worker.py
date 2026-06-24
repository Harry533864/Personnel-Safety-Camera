import logging
import os
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
        self._latest_frame_shape = None

        self._status_lock = threading.Lock()
        self._last_raw_frame_at = 0.0
        self._last_success_at = 0.0
        self._last_latency_ms = None
        self._last_error = None
        self._frame_count = 0
        self._infer_fps = FpsMeter()
        self._latest_overlay = {
            "detections": [],
            "zone_summary": [],
            "task_results": [],
            "system_state": "safe",
            "warning": False,
            "alarm": False,
        }
        self._latest_overlay_at = 0.0
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

    @staticmethod
    def _render_overlay_in_stream():
        return str(os.environ.get("CAM_RENDER_OVERLAY_IN_STREAM", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

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

    @staticmethod
    def _json_value(value):
        item = getattr(value, "item", None)
        if callable(item):
            try:
                return InferenceWorker._json_value(item())
            except Exception:
                pass
        if hasattr(value, "value"):
            return InferenceWorker._json_value(value.value)
        if isinstance(value, dict):
            return {str(k): InferenceWorker._json_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [InferenceWorker._json_value(v) for v in value]
        if isinstance(value, (str, bool, int, float)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _serialize_detection(detection):
        return {
            "bbox": [float(v) for v in getattr(detection, "bbox", [])],
            "class_id": int(getattr(detection, "class_id", 0)),
            "class_name": str(getattr(detection, "class_name", "")),
            "confidence": float(getattr(detection, "confidence", 0.0)),
            "center": [float(v) for v in getattr(detection, "center", [])],
            "foot_point": [float(v) for v in getattr(detection, "foot_point", [])],
            "roi_hits": InferenceWorker._json_value(
                getattr(detection, "roi_hits", []) or []
            ),
            "roi_contacts": InferenceWorker._json_value(
                getattr(detection, "roi_contacts", []) or []
            ),
        }

    @staticmethod
    def _zone_display_state(zone):
        person_count = int(getattr(zone, "person_count", 0))
        warning_count = int(getattr(zone, "warning_count", 0))
        roi_type = str(getattr(zone, "roi_type", ""))
        if person_count > 0:
            if roi_type == "warning_zone":
                return "warning", "#f59e0b"
            return "alarm", "#ef4444"
        if warning_count > 0:
            return "warning", "#f59e0b"
        return "safe", "#22c55e"

    @staticmethod
    def _serialize_zone(zone):
        display_status, display_color = InferenceWorker._zone_display_state(zone)
        return {
            "roi_id": str(getattr(zone, "roi_id", "")),
            "roi_name": str(getattr(zone, "roi_name", "")),
            "roi_type": str(getattr(zone, "roi_type", "")),
            "person_count": int(getattr(zone, "person_count", 0)),
            "warning_count": int(getattr(zone, "warning_count", 0)),
            "raw_active": bool(getattr(zone, "raw_active", False)),
            "raw_warning": bool(getattr(zone, "raw_warning", False)),
            "stable_active": bool(getattr(zone, "stable_active", False)),
            "stable_warning": bool(getattr(zone, "stable_warning", False)),
            "enter_counter": int(getattr(zone, "enter_counter", 0)),
            "exit_counter": int(getattr(zone, "exit_counter", 0)),
            "warning_enter_counter": int(getattr(zone, "warning_enter_counter", 0)),
            "warning_exit_counter": int(getattr(zone, "warning_exit_counter", 0)),
            "display_status": display_status,
            "display_color": display_color,
        }

    @classmethod
    def _serialize_overlay(cls, frame_result, task_results, frame_shape):
        height = int(frame_shape[0]) if frame_shape is not None else 0
        width = int(frame_shape[1]) if frame_shape is not None else 0
        if frame_result is None:
            return {
                "source_width": width,
                "source_height": height,
                "detections": [],
                "zone_summary": [],
                "task_results": cls._json_value(task_results or []),
                "system_state": "safe",
                "warning": False,
                "alarm": False,
            }

        state = getattr(frame_result, "system_state", "safe")
        state = getattr(state, "value", state)
        return {
            "source_width": width,
            "source_height": height,
            "detections": [
                cls._serialize_detection(detection)
                for detection in getattr(frame_result, "detections", []) or []
            ],
            "zone_summary": [
                cls._serialize_zone(zone)
                for zone in getattr(frame_result, "zone_summary", []) or []
            ],
            "task_results": cls._json_value(task_results or []),
            "system_state": str(state),
            "warning": bool(getattr(frame_result, "warning", False)),
            "alarm": bool(getattr(frame_result, "alarm", False)),
        }

    def overlay_state(self, max_age_sec=1.0):
        now = time.time()
        with self._status_lock:
            overlay = dict(self._latest_overlay)
            updated_at = self._latest_overlay_at
            last_error = self._last_error
            frames_inferred = self._frame_count

        age_sec = now - updated_at if updated_at else None
        stale = age_sec is None or (
            max_age_sec is not None and max_age_sec > 0 and age_sec > max_age_sec
        )
        if stale:
            overlay["detections"] = []

        with self._ai_lock:
            enabled = self._enabled
            model_loaded = self._model is not None

        overlay.update({
            "enable_infer": enabled,
            "model_loaded": model_loaded,
            "updated_at": self._format_time(updated_at),
            "age_sec": round(age_sec, 3) if age_sec is not None else None,
            "stale": stale,
            "last_error": last_error,
            "frames_inferred": frames_inferred,
        })
        return overlay

    def put_frame(self, frame):
        if not self._running or frame is None:
            return False

        with self._frame_lock:
            self._latest_raw_frame = frame
            self._latest_stream_frame = frame
            self._latest_frame_shape = frame.shape

        with self._status_lock:
            self._last_raw_frame_at = time.time()

        return True

    def get_frame(self):
        with self._frame_lock:
            frame = self._latest_stream_frame

        if frame is None:
            return None

        if not self._render_overlay_in_stream():
            return frame

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

    def get_frame_snapshot(self, include_overlay=False):
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

    def trigger_alarm_output(self, active=True, duration=0):
        with self._ai_lock:
            model = self._ensure_model_locked()

        model.set_alarm_output_for_test(bool(active))
        if active and duration > 0:
            time.sleep(duration)
            model.set_alarm_output_for_test(False)

    def set_alarm_output_channels(self, states):
        with self._ai_lock:
            model = self._model

        if model is None:
            return False

        return model.set_alarm_output_channels_for_test(states)

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
                    render_in_stream = self._render_overlay_in_stream()
                    infer_start = time.perf_counter()
                    result = model.inference(frame, render=render_in_stream)
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
                        self._latest_overlay = self._serialize_overlay(
                            getattr(model, "last_frame_result", None),
                            getattr(model, "last_task_results", []),
                            frame.shape,
                        )
                        self._latest_overlay_at = self._last_success_at

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
