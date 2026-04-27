import cv2
import subprocess
import time
import threading
import queue
import numpy as np

class CamManager:
    """
    单例硬件管理者（生产者）。
    负责独占式打开摄像头，以最高规格采集图像，统一管理硬件曝光，并将画面分发给所有 Worker。
    """
    def __init__(self, camera_id=0, width=1920, height=1080, fps=30):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.fps = fps
        
        self.workers = []
        self._is_running = False
        self._thread = None
        
        # 硬件曝光参数
        self._exposure_val = 0  # 默认 0 代表自动曝光，-13 到 -1 代表手动曝光
        self._exposure_changed = False
    
    def add_worker(self, worker):
        self.workers.append(worker)
        
    def set_exposure(self, value=0):
        """
        统一设置物理摄像头的曝光度（硬件层面）。
        所有的 CamWorker 都会收到此曝光度下的图像。
        """
        if value > 0 or value < -13:
            print("[CamManager] 曝光值必须在 0 到 -13 范围内  0[自动曝光]")
            return
        self._exposure_val = value
        self._exposure_changed = True
        print(f"[CamManager] 硬件曝光模式请求修改为: {'自动' if value == 0 else '手动(' + str(value) + ')'}")
    
    def _apply_exposure(self, cap):
        """
        应用曝光参数到摄像头句柄
        """
        if self._exposure_val == 0:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75) # 0.75 通常代表 DSHOW 下的自动模式
        else:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25) # 0.25 通常代表手动模式
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
        # 采集图像统一设置
        cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self._apply_exposure(cap) # 初始化应用曝光设置
        
        while self._is_running:
            # 检查是否需要修改曝光参数
            if self._exposure_changed:
                self._apply_exposure(cap)
                self._exposure_changed = False
            ret, frame = cap.read()
            if not ret:
                print("[Manager] 无法读取摄像头画面！")
                time.sleep(1)
                continue
            
            # 广播给所有注册的流处理工作线程
            for worker in self.workers:
                worker.put_frame(frame)
        cap.release()