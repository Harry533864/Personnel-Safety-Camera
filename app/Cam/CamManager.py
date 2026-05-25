import cv2
import time
import threading
import subprocess


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
    ):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.fps = fps
        self.fourcc = fourcc

        self.workers = []
        self._is_running = False
        self._thread = None

        self._exposure_val = 0
        self._exposure_changed = False
        self._need_reopen = False

    def add_worker(self, worker):
        self.workers.append(worker)

    def set_resolution(self, width, height):
        self.width = int(width)
        self.height = int(height)
        self._need_reopen = True
        print(f"[CamManager] 硬件分辨率请求修改为: {width}x{height}")

    def set_fps(self, fps):
        self.fps = int(fps)
        self._need_reopen = True
        print(f"[CamManager] 硬件帧率请求修改为: {fps}")

    def set_exposure(self, value=0):
        if value < 0:
            return

        self._exposure_val = value
        self._exposure_changed = True
        print(
            f"[CamManager] 硬件曝光模式请求修改为: "
            f"{'自动' if value == 0 else '手动(' + str(value) + ')'}"
        )

    def _apply_exposure(self):
        dev_path = self.camera_id

        if isinstance(dev_path, int) or (
            isinstance(dev_path, str) and dev_path.isdigit()
        ):
            dev_path = f"/dev/video{dev_path}"

        try:
            if self._exposure_val == 0:
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

                print(f"[CamManager] 已恢复 {dev_path} 自动曝光模式，尝试应用抗闪烁配置")

            else:
                exposure_int = int(float(self._exposure_val))
                command = f"auto_exposure=1,exposure_time_absolute={exposure_int}"

                subprocess.run(
                    ["v4l2-ctl", "-d", dev_path, "-c", command],
                    check=True,
                    capture_output=True,
                    text=True,
                )

                print(f"[CamManager] 已设置 {dev_path} 手动曝光: {exposure_int}")

        except FileNotFoundError:
            print("[CamManager] 致命异常: 未找到 v4l2-ctl 指令。")

        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip()
            print(f"[CamManager] 硬件曝光设置失败。错误码: {e.returncode}")
            print(f"[CamManager] 驱动底层反馈: {err_msg}")

    def start(self):
        if self._is_running:
            return

        self._is_running = True

        # 先启动 worker，再启动采集线程，避免前几帧直接丢掉
        for worker in self.workers:
            worker.start()

        self._thread = threading.Thread(
            target=self._capture_task,
            daemon=True,
            name="CamManagerCapture",
        )
        self._thread.start()

        print("[CamManager] 摄像头采集线程已启动...")

    def stop(self):
        self._is_running = False

        if self._thread:
            self._thread.join()
            self._thread = None

        for worker in self.workers:
            worker.stop()

        print("[Manager] 摄像头采集已停止。")

    def _build_pipeline(self):
        dev_path = self.camera_id

        if isinstance(dev_path, int) or (
            isinstance(dev_path, str) and dev_path.isdigit()
        ):
            dev_path = f"/dev/video{dev_path}"

        return (
            f"v4l2src device={dev_path} ! "
            f"image/jpeg, width={self.width}, height={self.height}, framerate={self.fps}/1 ! "
            f"jpegdec ! "
            f"videoconvert ! "
            f"video/x-raw, format=BGR ! "
            f"appsink drop=true max-buffers=1 sync=false"
        )

    def _capture_task(self):
        cap = cv2.VideoCapture(self._build_pipeline(), cv2.CAP_GSTREAMER)

        if not cap.isOpened():
            raise RuntimeError("[CamManager] 摄像头抓帧启动失败")

        while self._is_running:
            if self._need_reopen:
                print(
                    f"[CamManager] 正在以 "
                    f"{self.width}x{self.height}@{self.fps}FPS "
                    f"重启硬件采集流..."
                )

                cap.release()
                cap = cv2.VideoCapture(self._build_pipeline(), cv2.CAP_GSTREAMER)
                self._need_reopen = False
                self._exposure_changed = True

                if not cap.isOpened():
                    print("[Manager] 重启摄像头流失败！将重试...")
                    time.sleep(1.0)
                    continue

            if self._exposure_changed:
                self._apply_exposure()
                self._exposure_changed = False

            ret, frame = cap.read()

            if not ret or frame is None:
                print("[Manager] 无法从 GStreamer 管道读取画面！")
                time.sleep(1.0)
                continue

            for worker in self.workers:
                worker.put_frame(frame)

        cap.release()
        print("[CamManager] 采集线程安全退出")