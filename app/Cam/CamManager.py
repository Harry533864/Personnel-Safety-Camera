import cv2
import time
import threading

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
    
    def _apply_exposure(self, cap): #todo 待实现
        """
        通过 v4l2-ctl 直接向内核驱动发送 ioctl 指令以控制硬件曝光。
        需要系统已安装 v4l-utils (sudo apt-get install v4l-utils)。
        """
        pass 
        # if self._exposure_val == 0:
        #     cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3) # V4L2 自动曝光
        # else:
        #     cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1) # V4L2 手动曝光
        #     cap.set(cv2.CAP_PROP_EXPOSURE, self._exposure_val)
        
    
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