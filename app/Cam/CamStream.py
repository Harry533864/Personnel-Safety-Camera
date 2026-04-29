import cv2
import subprocess
import time
import threading
import queue

class CamStream:
    """
    流处理工作线程（消费者）。
    负责接收原始帧、进行软件层的处理（分辨率缩放、帧率控制），并推送到 FFmpeg。
    """
    def __init__(self, name, url, ffmpeg_exe="ffmpeg", width=1280, height=720, fps=15):
        self.name = name
        self.url = url
        self.ffmpeg_exe = ffmpeg_exe
        
        self.width = width
        self.height = height
        self.fps = max(1, fps)
        
        self.frame_queue = queue.Queue(maxsize=2)
        self._is_running = False
        self._thread = None
        self._need_ffmpeg_restart = True 

        self.set_lock = threading.Lock()

    def _build_ffmpeg_cmd(self, current_w=None, current_h=None, current_fps=None):
        return [
            self.ffmpeg_exe,
            "-loglevel", "warning", "-y",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{current_w}x{current_h}",
            "-r", str(current_fps),
            "-i", "-", "-an",
            "-vf", "format=yuv420p",
            
            # H.264 编码 (根据您提供的原始脚本参数优化)
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-profile:v", "baseline",
            "-level", "3.1",
            "-g", str(current_fps),
            "-keyint_min", str(current_fps),
            "-sc_threshold", "0",
            "-bf", "0",
            "-b:v", "1500k",
            "-maxrate", "1500k",
            "-bufsize", "300k",
            "-flush_packets", "1",
            "-f", "flv", 
            "-flvflags", "no_duration_filesize",
            self.url,
        ]
    
    def set_resolution(self, width, height):
        with self.set_lock:
            self.width = width
            self.height = height
            self._need_ffmpeg_restart = True
            print(f"[{self.name}] 目标分辨率变更为: {width}x{height}")
    
    def set_fps(self, fps):
        with self.set_lock:
            self.fps = max(1, fps)
            self._need_ffmpeg_restart = True
            print(f"[{self.name}] 目标推流帧率变更为: {self.fps}")
    
    def put_frame(self, frame):
        if not self._is_running:
            return
        try:
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
            frame_duration = 1.0 / current_fps
            
            if now < next_time:
                continue
            
            if now > next_time + frame_duration * 2:
                next_time = now + frame_duration
            else:
                next_time += frame_duration
                
            # 分辨率控制
            raw_h, raw_w = raw_frame.shape[:2]
            if current_w != raw_w or current_h != raw_h:
                frame = cv2.resize(raw_frame, (current_w, current_h))
            else:
                frame = raw_frame
                
            if need_restart:
                if proc:
                    if proc.stdin:
                        proc.stdin.close()
                    proc.wait()
                    
                ffmpeg_cmd = self._build_ffmpeg_cmd(current_w, current_h, current_fps)
                proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, bufsize=0)
                # self._need_ffmpeg_restart = False
                
            try:
                if proc.poll() is not None:
                    print(f"[{self.name}] FFmpeg 进程已退出，准备重启...")
                    self._need_ffmpeg_restart = True
                    continue
                proc.stdin.write(frame.tobytes())
            except BrokenPipeError:
                print(f"[{self.name}] 管道断开，准备重连...")
                # self._need_ffmpeg_restart = True
                with self.set_lock:
                    self._need_ffmpeg_restart = True
            except (ValueError, OSError) as exc:
                print(f"[{self.name}] 写入异常: {exc}")
                self._need_ffmpeg_restart = True
        
        if proc:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
