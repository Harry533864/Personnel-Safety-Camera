import cv2
import subprocess
import time
import threading
import queue
import numpy as np

class CamStream:
    """
    流处理工作线程（消费者）。
    负责接收原始帧、进行软件层的处理（分辨率缩放、帧率控制），并推送到 FFmpeg。
    """
    def __init__(self, name, url, ffmpeg_exe, width=1920, height=1080, fps=30):
        self.name = name
        self.url = url
        self.ffmpeg_exe = ffmpeg_exe
        
        # 目标推流参数
        self.width = width
        self.height = height
        self.fps = max(1, fps) # 帧率不能小于1
        
        self.frame_queue = queue.Queue(maxsize=2) # 仅保留最新帧，防止积压导致延迟
        self._is_running = False
        self._thread = None
        self._need_ffmpeg_restart = True # 标记是否需要重启 FFmpeg（如分辨率改变时）
        
        self.set_lock = threading.Lock() # 修改分辨率、帧率时使用的锁 防止ffmpeg_cmd与实际参数不一致
    
    def set_resolution(self, width, height):
        with self.set_lock: # 加锁防止推流参数与实际不一致
            self.width = width
            self.height = height
            self._need_ffmpeg_restart = True
            print(f"[{self.name}] 目标分辨率变更为: {width}x{height}")
    
    def set_fps(self, fps):
        """软件层面动态修改推流帧率"""
        with self.set_lock: # 加锁防止推流参数与实际不一致
            self.fps = max(1, fps)
            self._need_ffmpeg_restart = True
            print(f"[{self.name}] 目标推流帧率变更为: {self.fps}")
    
    def put_frame(self, frame):
        """接收来自 CamManager 的原始帧 (非阻塞)"""
        if not self._is_running:
            return
        try:
            # 如果队列满了，丢弃老帧，保持极低延迟
            if self.frame_queue.full():
                self.frame_queue.get_nowait()
            self.frame_queue.put_nowait(frame)
        except queue.Empty:
            pass
        except queue.Full:
            pass
    
    def start(self):
        if self._is_running: 
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._worker_task, daemon=True)
        self._thread.start()
        print(f"[CamStream[{self.name}]] 推流消费者已启动: {self.url}")
    
    def stop(self):
        self._is_running = False
        if self._thread:
            self._thread.join()
            print(f"[{self.name}] 推流消费者已停止")
    
    def _worker_task(self):
        proc = None
        next_time = time.time()
        
        while self._is_running:
            try:
                # 阻塞获取帧，设置超时是为了能够及时响应 _is_running 的变为 False
                raw_frame = self.frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            
            with self.set_lock:
                current_w = self.width
                current_h = self.height
                current_fps = self.fps
                need_restart = self._need_ffmpeg_restart
                self._need_ffmpeg_restart = False # 取出重启状态后立刻重置
            
            now = time.time()
            frame_duration = 1.0 / current_fps # 使用局部变量
            
            if now < next_time:
                # 时间未到，直接丢弃该帧（实现降帧）
                continue
            
            if now > next_time + frame_duration * 2:
                # 如果当前时间超前太多（可能发生了卡顿），重置基准时间，防止帧连续堆积爆发
                next_time = now + frame_duration
            else:
                next_time += frame_duration
                
            # 分辨率控制
            raw_h, raw_w = raw_frame.shape[:2]
            if current_w != raw_w or current_h != raw_h:
                frame = cv2.resize(raw_frame, (current_w, current_h))
            else:
                frame = raw_frame
                
            # ffmpeg 管道
            if need_restart:
                if proc:
                    proc.stdin.close()
                    proc.wait()
                    
                ffmpeg_cmd = [
                    self.ffmpeg_exe,
                    "-loglevel", "error", "-y",
                    "-f", "rawvideo", "-pix_fmt", "bgr24",
                    "-s", f"{current_w}x{current_h}",
                    "-r", str(current_fps),  # 告诉 FFmpeg 预期的帧率
                    "-i", "-", "-an",
                    "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                    "-pix_fmt", "yuv420p",
                    "-g", str(current_fps * 2),
                    "-maxrate", "2M", "-bufsize", "4M",
                    "-f", "flv", self.url
                ]
                proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
                # self._need_ffmpeg_restart = False # 在上锁获取数据快照时已经重置为False了
                
            # 写入数据
            try:
                proc.stdin.write(frame.tobytes())
            except BrokenPipeError:
                # 处理由于网络或服务端异常导致的管道断开，触发下一次循环的重启
                print(f"[{self.name}] 管道断开，准备重连...")
                with self.set_lock:
                    self._need_ffmpeg_restart = True
            except Exception as e:
                print(f"[{self.name}] 写入异常: {e}")
        
        # 退出清理
        if proc and proc.stdin:
            proc.stdin.close()
            proc.wait()
         
