import cv2
import os
import time
import threading
import subprocess
import logging

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
        camera_source="usb",
        csi_sensor_id=0,
        csi_flip_method=0,
        direct_stream_url=None,
        width=1280,
        height=720,
        fps=15,
        fourcc="MJPG",
        usb_decoder="auto",
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
        self.usb_decoder = self._normalize_usb_decoder(usb_decoder)

        self.workers = []
        self._is_running = False
        self._thread = None
        self._state_lock = threading.RLock()
        self._workers_lock = threading.RLock()
        self.logger = logging.getLogger(__name__)

        self._exposure_val = 0
        self._exposure_changed = False
        self._gain_val = 0
        self._gain_changed = False
        self._white_balance_mode = "continuous"
        self._white_balance_changed = False
        self._power_line_frequency = 1
        self._power_line_changed = False
        self._need_reopen = False
        self._reconnect_interval = 1.0
        self._camera_opened = False
        self._last_frame_at = 0.0
        self._last_error = None
        self._open_fail_count = 0
        self._read_fail_count = 0
        self._last_pipeline = None
        self._active_decoder = None
        self._capture_fps = FpsMeter()

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
                "actual_capture_fps": self._capture_fps.fps(),
                "fourcc": self.fourcc,
                "usb_decoder": self.usb_decoder,
                "active_decoder": self._active_decoder,
                "running": self._is_running,
                "thread_alive": bool(self._thread and self._thread.is_alive()),
                "camera_opened": self._camera_opened,
                "last_frame_at": self._format_time(self._last_frame_at),
                "last_error": self._last_error,
                "open_fail_count": self._open_fail_count,
                "read_fail_count": self._read_fail_count,
                "need_reopen": self._need_reopen,
                "exposure": self._exposure_val,
                "exposure_pending": self._exposure_changed,
                "gain": self._gain_val,
                "gain_pending": self._gain_changed,
                "white_balance": self._white_balance_mode,
                "white_balance_pending": self._white_balance_changed,
                "power_line_frequency": self._power_line_frequency,
                "power_line_pending": self._power_line_changed,
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

    def set_gain(self, value=0):
        try:
            gain = int(float(value))
        except (TypeError, ValueError):
            return
        if gain < 0:
            return

        with self._state_lock:
            self._gain_val = min(gain, 255)
            self._gain_changed = True
        self.logger.info("Camera gain requested: %s", self._gain_val)

    def set_white_balance(self, mode="continuous"):
        value = str(mode or "continuous").strip().lower()
        aliases = {
            "auto": "continuous",
            "on": "continuous",
            "true": "continuous",
            "1": "continuous",
            "continuous": "continuous",
            "off": "off",
            "manual": "off",
            "false": "off",
            "0": "off",
        }
        value = aliases.get(value, "continuous")

        with self._state_lock:
            self._white_balance_mode = value
            self._white_balance_changed = True
        self.logger.info("Camera white balance requested: %s", value)

    def set_power_line_frequency(self, value=1):
        aliases = {
            "disabled": 0,
            "off": 0,
            "0": 0,
            "50": 1,
            "50hz": 1,
            "1": 1,
            "60": 2,
            "60hz": 2,
            "2": 2,
        }
        raw = str(value if value is not None else 1).strip().lower().replace(" ", "")
        if raw in aliases:
            frequency = aliases[raw]
        else:
            try:
                frequency = int(float(raw))
            except (TypeError, ValueError):
                frequency = 1
        if frequency not in {0, 1, 2}:
            frequency = 1

        with self._state_lock:
            self._power_line_frequency = frequency
            self._power_line_changed = True
        self.logger.info("Camera power-line frequency requested: %s", frequency)

    def _v4l2_device_path(self):
        dev_path = self.camera_id
        if isinstance(dev_path, int) or (
            isinstance(dev_path, str) and dev_path.isdigit()
        ):
            dev_path = f"/dev/video{dev_path}"
        return dev_path

    def _set_v4l2_controls(self, control_string):
        dev_path = self._v4l2_device_path()
        try:
            subprocess.run(
                ["v4l2-ctl", "-d", dev_path, "-c", control_string],
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except FileNotFoundError:
            self.logger.error("v4l2-ctl command not found")
        except subprocess.CalledProcessError as e:
            self.logger.error(
                "Camera control command failed: controls=%s returncode=%s stderr=%s",
                control_string,
                e.returncode,
                e.stderr.strip(),
            )
        return False

    def _apply_exposure(self):
        if self.camera_source == "csi":
            self.logger.info("Skipping v4l2 exposure controls for CSI camera")
            return

        with self._state_lock:
            exposure_val = self._exposure_val

        try:
            if exposure_val == 0:
                self._set_v4l2_controls("auto_exposure=3")

                self.logger.info(
                    "Camera auto exposure restored for %s",
                    self._v4l2_device_path(),
                )

            else:
                exposure_int = int(float(exposure_val))
                command = f"auto_exposure=1,exposure_time_absolute={exposure_int}"

                self._set_v4l2_controls(command)

                self.logger.info(
                    "Camera manual exposure set for %s: %s",
                    self._v4l2_device_path(),
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

    def _apply_gain(self):
        if self.camera_source == "csi":
            self.logger.info("Skipping v4l2 gain controls for CSI camera")
            return

        with self._state_lock:
            gain_val = int(self._gain_val)

        if self._set_v4l2_controls(f"gain={gain_val}"):
            self.logger.info(
                "Camera gain set for %s: %s",
                self._v4l2_device_path(),
                gain_val,
            )

    def _apply_white_balance(self):
        if self.camera_source == "csi":
            self.logger.info("Skipping v4l2 white balance controls for CSI camera")
            return

        with self._state_lock:
            white_balance_mode = self._white_balance_mode

        enabled = 1 if white_balance_mode == "continuous" else 0
        if self._set_v4l2_controls(f"white_balance_automatic={enabled}"):
            self.logger.info(
                "Camera white balance set for %s: %s",
                self._v4l2_device_path(),
                white_balance_mode,
            )
            return

        fallback = f"white_balance_temperature_auto={enabled}"
        if self._set_v4l2_controls(fallback):
            self.logger.info(
                "Camera white balance fallback set for %s: %s",
                self._v4l2_device_path(),
                white_balance_mode,
            )

    def _apply_power_line_frequency(self):
        if self.camera_source == "csi":
            self.logger.info("Skipping v4l2 power-line controls for CSI camera")
            return

        with self._state_lock:
            frequency = int(self._power_line_frequency)

        if self._set_v4l2_controls(f"power_line_frequency={frequency}"):
            self.logger.info(
                "Camera power-line frequency set for %s: %s",
                self._v4l2_device_path(),
                frequency,
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

    @staticmethod
    def _normalize_usb_decoder(value):
        decoder = str(value or "auto").strip().lower()
        aliases = {
            "hw": "nvv4l2decoder",
            "hardware": "nvv4l2decoder",
            "software": "jpegdec",
            "sw": "jpegdec",
        }
        decoder = aliases.get(decoder, decoder)
        if decoder not in {"auto", "jpegdec", "nvjpegdec", "nvv4l2decoder"}:
            return "auto"
        return decoder

    def _build_pipeline_candidates(self):
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

                return [(
                    None,
                    (
                        f"nvarguscamerasrc sensor-id={self.csi_sensor_id} ! "
                        f"{capture_caps} ! "
                        f"tee name=t "
                        f"t. ! {direct_branch} "
                        f"t. ! queue leaky=downstream max-size-buffers=1 ! "
                        f"{appsink_branch}"
                    ),
                )]

            return [(
                None,
                (
                    f"nvarguscamerasrc sensor-id={self.csi_sensor_id} ! "
                    f"{capture_caps} ! "
                    f"{appsink_branch}"
                ),
            )]

        decoder_order = [self.usb_decoder]
        if self.usb_decoder == "auto":
            decoder_order = ["nvv4l2decoder", "jpegdec"]

        return [
            (decoder, self._build_usb_pipeline(decoder, width, height, fps))
            for decoder in decoder_order
        ]

    def _build_pipeline(self):
        candidates = self._build_pipeline_candidates()
        if candidates:
            return candidates[0][1]
        return ""

    def _build_usb_pipeline(self, decoder, width, height, fps):
        dev_path = self.camera_id

        if isinstance(dev_path, int) or (
            isinstance(dev_path, str) and dev_path.isdigit()
        ):
            dev_path = f"/dev/video{dev_path}"

        source = (
            f"v4l2src device={dev_path} ! "
            f"image/jpeg, width={width}, height={height}, framerate={fps}/1 ! "
        )

        if decoder == "nvv4l2decoder":
            decode = (
                f"jpegparse ! "
                f"nvv4l2decoder mjpeg=1 enable-max-performance=1 ! "
                f"nvvidconv ! "
                f"video/x-raw, format=BGRx ! "
                f"videoconvert ! "
                f"video/x-raw, format=BGR ! "
            )
        elif decoder == "nvjpegdec":
            decode = (
                f"jpegparse ! "
                f"nvjpegdec ! "
                f"nvvidconv ! "
                f"video/x-raw, format=BGRx ! "
                f"videoconvert ! "
                f"video/x-raw, format=BGR ! "
            )
        else:
            decode = (
                f"jpegdec ! "
                f"videoconvert ! "
                f"video/x-raw, format=BGR ! "
            )

        return (
            f"{source}"
            f"{decode}"
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
        candidates = self._build_pipeline_candidates()

        for decoder, pipeline in candidates:
            self._set_status(_last_pipeline=pipeline, _active_decoder=decoder)

            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            if cap.isOpened():
                self._set_status(_camera_opened=True, _last_error=None)
                self.logger.info(
                    "Camera capture opened with decoder=%s",
                    decoder or "default",
                )
                return cap

            cap.release()
            self.logger.warning(
                "Camera open failed with decoder=%s; trying next candidate",
                decoder or "default",
            )

        with self._state_lock:
            self._camera_opened = False
            self._active_decoder = None
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
                self._gain_changed = True
                self._white_balance_changed = True
                self._power_line_changed = True
            return need_reopen

    def _consume_exposure_flag(self):
        with self._state_lock:
            exposure_changed = self._exposure_changed
            if exposure_changed:
                self._exposure_changed = False
            return exposure_changed

    def _consume_gain_flag(self):
        with self._state_lock:
            gain_changed = self._gain_changed
            if gain_changed:
                self._gain_changed = False
            return gain_changed

    def _consume_white_balance_flag(self):
        with self._state_lock:
            white_balance_changed = self._white_balance_changed
            if white_balance_changed:
                self._white_balance_changed = False
            return white_balance_changed

    def _consume_power_line_flag(self):
        with self._state_lock:
            power_line_changed = self._power_line_changed
            if power_line_changed:
                self._power_line_changed = False
            return power_line_changed

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

                if self._consume_gain_flag():
                    self._apply_gain()

                if self._consume_white_balance_flag():
                    self._apply_white_balance()

                if self._consume_power_line_flag():
                    self._apply_power_line_frequency()

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
