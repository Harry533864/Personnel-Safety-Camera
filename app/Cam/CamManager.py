import cv2
import os
import time
import threading
import subprocess
import logging


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
        camera_source="usb",
        csi_sensor_id=0,
        csi_flip_method=0,
        direct_stream_url=None,
        width=1280,
        height=720,
        fps=15,
        fourcc="MJPG",
    ):
        self.camera_id = camera_id
        self.camera_source = str(camera_source or "usb").lower()
        self.csi_sensor_id = int(csi_sensor_id)
        self.csi_flip_method = int(csi_flip_method)
        self.direct_stream_url = direct_stream_url
        self.width = width
        self.height = height
        self.fps = fps
        self.fourcc = fourcc

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
            return {
                "camera_id": self.camera_id,
                "camera_source": self.camera_source,
                "csi_sensor_id": self.csi_sensor_id,
                "csi_flip_method": self.csi_flip_method,
                "direct_stream_enabled": bool(self.direct_stream_url),
                "direct_stream_url": self.direct_stream_url,
                "width": self.width,
                "height": self.height,
                "fps": self.fps,
                "fourcc": self.fourcc,
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
        if self.camera_source == "csi":
            self.logger.info("Skipping v4l2 exposure controls for CSI camera")
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
        with self._state_lock:
            width = self.width
            height = self.height
            fps = self.fps

        if self.camera_source == "csi":
            capture_caps = (
                f"video/x-raw(memory:NVMM), "
                f"width={width}, height={height}, framerate={fps}/1"
            )
            appsink_branch = (
                f"nvvidconv flip-method={self.csi_flip_method} ! "
                f"video/x-raw, format=BGRx ! "
                f"videoconvert ! "
                f"video/x-raw, format=BGR ! "
                f"appsink drop=true max-buffers=1 sync=false"
            )

            if self.direct_stream_url:
                direct_branch = (
                    f"queue leaky=downstream max-size-buffers=2 ! "
                    f"nvvidconv flip-method={self.csi_flip_method} ! "
                    f"video/x-raw, format=I420 ! "
                    f"x264enc "
                    f"bitrate={self._suggest_bitrate_kbps(width, height, fps)} "
                    f"speed-preset=ultrafast "
                    f"tune=zerolatency "
                    f"vbv-buf-capacity={self._direct_vbv_ms()} "
                    f"rc-lookahead=0 "
                    f"sync-lookahead=0 "
                    f"key-int-max={self._direct_key_int(fps)} "
                    f"bframes=0 "
                    f"threads={self._x264_threads()} "
                    f"sliced-threads={str(self._x264_sliced_threads()).lower()} "
                    f"byte-stream=false ! "
                    f"h264parse config-interval=1 ! "
                    f"flvmux streamable=true ! "
                    f"rtmpsink location={self.direct_stream_url} sync=false async=false"
                )

                return (
                    f"nvarguscamerasrc sensor-id={self.csi_sensor_id} ! "
                    f"{capture_caps} ! "
                    f"tee name=t "
                    f"t. ! {direct_branch} "
                    f"t. ! queue leaky=downstream max-size-buffers=1 ! "
                    f"{appsink_branch}"
                )

            return (
                f"nvarguscamerasrc sensor-id={self.csi_sensor_id} ! "
                f"{capture_caps} ! "
                f"{appsink_branch}"
            )

        dev_path = self.camera_id

        if isinstance(dev_path, int) or (
            isinstance(dev_path, str) and dev_path.isdigit()
        ):
            dev_path = f"/dev/video{dev_path}"

        return (
            f"v4l2src device={dev_path} ! "
            f"image/jpeg, width={width}, height={height}, framerate={fps}/1 ! "
            f"jpegdec ! "
            f"videoconvert ! "
            f"video/x-raw, format=BGR ! "
            f"appsink drop=true max-buffers=1 sync=false"
        )

    @staticmethod
    def _suggest_bitrate_kbps(w, h, fps):
        pixels = int(w) * int(h)
        if pixels >= 2560 * 1440:
            return int(os.environ.get("CSI_DIRECT_BITRATE_KBPS", "15000"))
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
    def _direct_key_int(fps):
        default_key_int = max(1, min(int(fps), 10))
        raw = os.environ.get("CSI_DIRECT_KEY_INT")
        if raw is None or raw == "":
            return default_key_int
        try:
            return max(1, int(raw))
        except ValueError:
            return default_key_int

    @staticmethod
    def _direct_vbv_ms():
        raw = os.environ.get("CSI_DIRECT_VBV_MS", "100")
        try:
            return max(0, int(raw))
        except ValueError:
            return 100

    def _open_capture(self):
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

                with self._workers_lock:
                    workers = list(self.workers)

                for worker in workers:
                    worker.put_frame(frame)

        finally:
            if cap is not None:
                cap.release()
            self._set_status(_camera_opened=False)
            self.logger.info("Camera capture thread exited")
