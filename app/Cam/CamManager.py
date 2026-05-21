import cv2
import time
import threading
import subprocess

class CamManager:
    """
    单例硬件管理者（生产者）。
    负责独占式打开摄像头，以最高规格采集图像，统一管理硬件曝光，并将画面分发给所有 Worker。
    """
    def __init__(self, camera_id="/dev/video0", width=1280, height=720, fps=15, fourcc="MJPG"):
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

    def add_worker(self, worker):
        self.workers.append(worker)
        
    def set_exposure(self, value=0):
        if value < 0:
            return
        
        self._exposure_val = value
        self._exposure_changed = True
        print(f"[CamManager] 硬件曝光模式请求修改为: {'自动' if value == 0 else '手动(' + str(value) + ')'}")
    
    def _apply_exposure(self):
        # 解析标准设备节点路径
        dev_path = self.camera_id
        if isinstance(dev_path, int) or (isinstance(dev_path, str) and dev_path.isdigit()):
            dev_path = f"/dev/video{dev_path}"

        try:
            if self._exposure_val == 0:
                # 恢复自动曝光
                subprocess.run(
                    ["v4l2-ctl", "-d", dev_path, "-c", "auto_exposure=3"],
                    check=True, 
                    capture_output=True, text=True
                )
                print(f"[CamManager] 已恢复 {dev_path} 自动曝光模式")
            else:
                # 1. 强制转换为整数，剔除浮点数带来的非法传参风险
                exposure_int = int(float(self._exposure_val))
                
                # 2. 将模式切换和数值修改合并为一条指令
                # 让 v4l2-ctl 在一次 ioctl 事务中处理，避免硬件响应时差带来的 inactive 锁冲突
                command = f"auto_exposure=1,exposure_time_absolute={exposure_int}"
                
                subprocess.run(
                    ["v4l2-ctl", "-d", dev_path, "-c", command],
                    check=True, 
                    capture_output=True, text=True
                )
                print(f"[CamManager] 已设置 {dev_path} 手动曝光: {exposure_int}")

        except FileNotFoundError:
            print("[CamManager] 致命异常: 未找到 v4l2-ctl 指令。")
        except subprocess.CalledProcessError as e:
            # 捕获并打印底层真实的报错原因，而不是只报错误码 1
            err_msg = e.stderr.strip()
            print(f"[CamManager] 硬件曝光设置失败。错误码: {e.returncode}")
            print(f"[CamManager] 驱动底层反馈: {err_msg}")
         
    
    def start(self):
        if self._is_running: return
        self._is_running = True
        self._thread = threading.Thread(target=self._capture_task, daemon=True)
        self._thread.start()
        print("[CamManager] 摄像头采集线程已启动...")
        for worker in self.workers:
            worker.start()
    
    def stop(self):
        self._is_running = False
        if self._thread:
            self._thread.join()
        for w in self.workers:
            w.stop()
        print("[Manager] 摄像头采集已停止。")
    
    def _capture_task(self):
        # 自动兼容整数 0 或 字符串 "/dev/video0"
        dev_path = self.camera_id
        if isinstance(dev_path, int) or (isinstance(dev_path, str) and dev_path.isdigit()):
            dev_path = f"/dev/video{dev_path}"
        
        gst_pipeline = (
            f"v4l2src device={dev_path} ! "
            f"image/jpeg, width={self.width}, height={self.height} ! "
            f"jpegdec ! "  # 利用通用的 jpegdec 独立线程进行高速软解
            f"videoconvert ! "
            f"video/x-raw, format=BGR ! "
            f"appsink drop=true max-buffers=1 sync=false"
        )
        cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            raise RuntimeError(f"GStreamer 无法打开摄像头")
        
        while self._is_running:
            if self._exposure_changed:
                self._apply_exposure()
                self._exposure_changed = False
                
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[Manager] 无法从 GStreamer 管道读取画面！")
                time.sleep(1)
                continue
            
            for worker in self.workers:
                worker.put_frame(frame)
                
        cap.release()
        print("[CamManager] 采集线程安全退出")