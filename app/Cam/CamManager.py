import cv2
import os
import time
import threading
import subprocess
import logging

from app.Cam.capture_backends import BaumerNeoApiCapture
from app.Cam.fps_meter import FpsMeter


class CamManager:
    """
    单例硬件管理者（生产者）。
    负责独占式打开摄像头，以最高规格采集图像，统一管理硬件曝光，
    并将画面分发给所有 Worker。

    这个版本基本保持你的原逻辑：
    - 采集线程独立运行。
    - GStreamer appsink 使用 drop=true max-buffers=1 sync=false。
    - 每个 worker 内部自己只保留最新帧。
    """

    def __init__(
        self,
        camera_id="/dev/video0",
        width=1280,
        height=720,
        fps=15,
        fourcc="MJPG",
        capture_backend=None,
    ):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.fps = fps
        self.fourcc = fourcc
        self.capture_backend = (
            capture_backend
            or os.environ.get("CAM_CAPTURE_BACKEND")
            or os.environ.get("CAPTURE_BACKEND")
            or "v4l2"
        ).strip().lower()

        self.workers = []
        self._is_running = False
        self._thread = None
        self._state_lock = threading.RLock()
        self._workers_lock = threading.RLock()
        self.logger = logging.getLogger(__name__)

        self._exposure_val = 0
        self._exposure_changed = False
        self._need_reopen = False
        self._reconnect_interval = 1.0
        self._camera_opened = False
        self._last_frame_at = 0.0
        self._last_error = None
        self._open_fail_count = 0
        self._read_fail_count = 0
        self._last_pipeline = None
        self._capture_fps = FpsMeter()

    def get_max_resolution(self):
        env_width = os.environ.get("CAMERA_MAX_WIDTH") or os.environ.get("BAUMER_MAX_WIDTH")
        env_height = os.environ.get("CAMERA_MAX_HEIGHT") or os.environ.get("BAUMER_MAX_HEIGHT")
        if env_width and env_height:
            return int(env_width), int(env_height)

        if self.capture_backend in {"baumer", "baumer_neoapi", "neoapi"}:
            return 2448, 2048

        return max(1, int(self.width)), max(1, int(self.height))

    def _format_time(self, timestamp):
        if not timestamp:
            return None
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(timestamp))

    def _set_status(self, **kwargs):
        with self._state_lock:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def get_status(self):
        with self._workers_lock:
            worker_count = len(self.workers)

        with self._state_lock:
            max_width, max_height = self.get_max_resolution()
            return {
                "camera_id": self.camera_id,
                "width": self.width,
                "height": self.height,
                "max_width": max_width,
                "max_height": max_height,
                "fps": self.fps,
                "actual_capture_fps": self._capture_fps.fps(),
                "fourcc": self.fourcc,
                "capture_backend": self.capture_backend,
                "running": self._is_running,
                "thread_alive": bool(self._thread and self._thread.is_alive()),
                "camera_opened": self._camera_opened,
                "last_frame_at": self._format_time(self._last_frame_at),
                "last_error": self._last_error,
                "open_fail_count": self._open_fail_count,
                "read_fail_count": self._read_fail_count,
                "need_reopen": self._need_reopen,
                "exposure_pending": self._exposure_changed,
                "worker_count": worker_count,
                "last_pipeline": self._last_pipeline,
            }

    def add_worker(self, worker):
        with self._workers_lock:
            self.workers.append(worker)

    def set_resolution(self, width, height):
        with self._state_lock:
            self.width = int(width)
            self.height = int(height)
            self._need_reopen = True
        self.logger.info("Camera resolution requested: %sx%s", width, height)

    def set_fps(self, fps):
        with self._state_lock:
            self.fps = int(fps)
            self._need_reopen = True
        self.logger.info("Camera FPS requested: %s", fps)

    def set_exposure(self, value=0):
        if value < 0:
            return

        with self._state_lock:
            self._exposure_val = value
            self._exposure_changed = True
        self.logger.info("Camera exposure requested: %s", value)

    def _apply_exposure(self):
        if self.capture_backend in {"baumer", "baumer_neoapi", "neoapi"}:
            self.logger.info(
                "Baumer exposure will be applied when capture is opened/reopened"
            )
            return

        dev_path = self.camera_id
        with self._state_lock:
            exposure_val = self._exposure_val

        if isinstance(dev_path, int) or (
            isinstance(dev_path, str) and dev_path.isdigit()
        ):
            dev_path = f"/dev/video{dev_path}"

        try:
            if exposure_val == 0:
                subprocess.run(
                    ["v4l2-ctl", "-d", dev_path, "-c", "auto_exposure=3"],
                    check=True,
                    capture_output=True,
                    text=True,
                )

                subprocess.run(
                    ["v4l2-ctl", "-d", dev_path, "-c", "power_line_frequency=1"],
                    capture_output=True,
                    text=True,
                )

                self.logger.info(
                    "Camera auto exposure restored for %s", dev_path
                )

            else:
                exposure_int = int(float(exposure_val))
                command = f"auto_exposure=1,exposure_time_absolute={exposure_int}"

                subprocess.run(
                    ["v4l2-ctl", "-d", dev_path, "-c", command],
                    check=True,
                    capture_output=True,
                    text=True,
                )

                self.logger.info(
                    "Camera manual exposure set for %s: %s",
                    dev_path,
                    exposure_int,
                )

        except FileNotFoundError:
            self.logger.error("v4l2-ctl command not found")

        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip()
            self.logger.error(
                "Camera exposure command failed: returncode=%s stderr=%s",
                e.returncode,
                err_msg,
            )

    def start(self):
        if self._is_running and self._thread and self._thread.is_alive():
            return

        self._is_running = True

        # 先启动 worker，再启动采集线程，避免前几帧直接丢掉
        with self._workers_lock:
            workers = list(self.workers)

        for worker in workers:
            worker.start()

        self._thread = threading.Thread(
            target=self._capture_task,
            daemon=True,
            name="CamManagerCapture",
        )
        self._thread.start()

        self.logger.info("Camera capture thread started")

    def stop(self):
        self._is_running = False

        if self._thread:
            self._thread.join()
            self._thread = None

        with self._workers_lock:
            workers = list(self.workers)

        for worker in workers:
            worker.stop()

        self.logger.info("Camera capture stopped")

    def _build_pipeline(self):
        dev_path = self.camera_id

        if isinstance(dev_path, int) or (
            isinstance(dev_path, str) and dev_path.isdigit()
        ):
            dev_path = f"/dev/video{dev_path}"

        with self._state_lock:
            width = self.width
            height = self.height
            fps = self.fps

        return (
            f"v4l2src device={dev_path} ! "
            f"image/jpeg, width={width}, height={height}, framerate={fps}/1 ! "
            f"jpegdec ! "
            f"videoconvert ! "
            f"video/x-raw, format=BGR ! "
            f"appsink drop=true max-buffers=1 sync=false"
        )

    def _open_capture(self):
        if self.capture_backend in {"baumer", "baumer_neoapi", "neoapi"}:
            with self._state_lock:
                capture = BaumerNeoApiCapture(
                    width=self.width,
                    height=self.height,
                    fps=self.fps,
                    exposure_us=self._exposure_val,
                    pixel_format=os.environ.get("BAUMER_PIXEL_FORMAT", "BGR8"),
                    connect_retries=int(os.environ.get("BAUMER_CONNECT_RETRIES", "3")),
                )
            self._set_status(_last_pipeline=capture.describe())
            if capture.open():
                self._set_status(_camera_opened=True, _last_error=None)
                self.logger.info("Baumer neoAPI capture opened")
                return capture

            with self._state_lock:
                self._camera_opened = False
                self._open_fail_count += 1
                self._last_error = capture.last_error or "baumer camera open failed"
            self.logger.warning("Baumer camera open failed; will retry")
            return None

        pipeline = self._build_pipeline()
        self._set_status(_last_pipeline=pipeline)

        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            self._set_status(_camera_opened=True, _last_error=None)
            self.logger.info("Camera capture opened")
            return cap

        cap.release()
        with self._state_lock:
            self._camera_opened = False
            self._open_fail_count += 1
            self._last_error = "camera open failed"

        self.logger.warning("Camera open failed; will retry")
        return None

    def _consume_reopen_flag(self):
        with self._state_lock:
            need_reopen = self._need_reopen
            if need_reopen:
                self._need_reopen = False
                self._exposure_changed = True
            return need_reopen

    def _consume_exposure_flag(self):
        with self._state_lock:
            exposure_changed = self._exposure_changed
            if exposure_changed:
                self._exposure_changed = False
            return exposure_changed

    def _capture_task(self):
        cap = None

        try:
            while self._is_running:
                if cap is None or not cap.isOpened():
                    cap = self._open_capture()
                    if cap is None:
                        time.sleep(self._reconnect_interval)
                        continue

                if self._consume_reopen_flag():
                    self.logger.info(
                        "Restarting camera capture: %sx%s@%s",
                        self.width,
                        self.height,
                        self.fps,
                    )
                    cap.release()
                    cap = None
                    continue

                if self._consume_exposure_flag():
                    self._apply_exposure()

                ret, frame = cap.read()

                if not ret or frame is None:
                    with self._state_lock:
                        self._camera_opened = False
                        self._read_fail_count += 1
                        self._last_error = "camera read failed"
                    self.logger.warning("Camera read failed; reopening")
                    cap.release()
                    cap = None
                    time.sleep(self._reconnect_interval)
                    continue

                self._set_status(
                    _camera_opened=True,
                    _last_frame_at=time.time(),
                    _last_error=None,
                )
                self._capture_fps.mark()

                with self._workers_lock:
                    workers = list(self.workers)

                for worker in workers:
                    worker.put_frame(frame)

        finally:
            if cap is not None:
                cap.release()
            self._set_status(_camera_opened=False)
            self.logger.info("Camera capture thread exited")
