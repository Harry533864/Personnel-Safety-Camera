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
    
    def _apply_exposure(self, cap):    
        if self._exposure_val == 0:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3) # V4L2 自动曝光
        else:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1) # V4L2 手动曝光
            cap.set(cv2.CAP_PROP_EXPOSURE, self._exposure_val)
    
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
        cap = cv2.VideoCapture(self.camera_id, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError(f"无法打开摄像头: {self.camera_id}")

        if self.fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self._apply_exposure(cap)
        
        while self._is_running:
            if self._exposure_changed:
                self._apply_exposure(cap)
                self._exposure_changed = False
            ret, frame = cap.read()
            if not ret:
                print("[Manager] 无法读取摄像头画面！")
                time.sleep(1)
                continue
            
            for worker in self.workers:
                worker.put_frame(frame)
        cap.release()
