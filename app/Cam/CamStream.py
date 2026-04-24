import cv2
import subprocess
import time
import threading

class CamStream:
    def __init__(self, url, ffmpeg_exe="ffmpeg", name="cam_default", width=1920, height=1080, fps=30):
        self.name = name
        self.url = url
        self.ffmpeg_exe = ffmpeg_exe # 默认Linux下的 "ffmpeg" windows下需要直接传入路径
        self.width = width
        self.height = height
        self.fps = fps
        
        self._is_running = False
        self._thread = None
        self._res_changed = False  # 分辨率改变标记
        self._exposure_val = 0  # 0 代表自动曝光，-13 -> -1 整数代表手动曝光值
        self._exposure_changed = False
        
    def set_resolution(self, width, height):
        """动态修改分辨率（会导致推流短暂中断重启）"""
        self.width = width
        self.height = height
        self._res_changed = True
        print(f"分辨率修改为: {width}x{height}")
        
    def set_exposure(self, value=None):
        """
        设置曝光: 
        value = 0: 自动曝光
        value = -1 ~ -13: 手动曝光，数值越小越暗
        """
        if value > 0 or value < -13:
            print(f"曝光值必须在 0-13 范围内")
            return
        self._exposure_val = value
        self._exposure_changed = True
        print(f"曝光模式请求修改为: {'自动' if value is None else '手动(' + str(value) + ')'}")

    def start(self):
        """启动后台推流线程"""
        if self._is_running:
            return
        self._is_running = True
        # 使用 daemon=True，主程序退出时，该线程也会自动强制退出
        self._thread = threading.Thread(target=self._stream_task, daemon=True)
        self._thread.start()
        print("后台推流已启动...")

    def stop(self):
        """停止推流"""
        self._is_running = False
        if self._thread is not None:
            self._thread.join()
            print("推流已停止。")
            
    def _apply_camera_settings(self, cap):
        """应用当前类属性到摄像头硬件"""
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        
        # 曝光设置
        if self._exposure_val == 0:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75) # 0.75 通常代表 DSHOW 下的自动模式
        else:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25) # 0.25 通常代表手动模式
            cap.set(cv2.CAP_PROP_EXPOSURE, self._exposure_val)

    def _stream_task(self):
        """实际执行推流的后台任务"""
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        # 推流配置初始化
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # 缓存区设置
        # cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width) # 分辨率设置
        # cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        # cap.set(cv2.CAP_PROP_FPS, self.fps) # 帧率设置
        self._apply_camera_settings(cap)

        proc = None
        frame_interval = 1.0 / self.fps
        next_time = time.time()

        try:
            while self._is_running:
                # 1. 检查分辨率是否改变，若改变则关闭旧进程
                if self._res_changed:
                    if proc:
                        proc.stdin.close()
                        proc.wait()
                        proc = None
                    self._apply_camera_settings(cap)
                    self._res_changed = False

                # 2. 检查曝光是否改变
                if self._exposure_changed:
                    self._apply_camera_settings(cap)
                    self._exposure_changed = False

                ret, frame = cap.read()
                if not ret: break

                # 3. 延迟初始化或重启 FFmpeg 进程
                if proc is None:
                    h, w = frame.shape[:2]
                    ffmpeg_cmd = [
                        self.ffmpeg_exe,
                        "-loglevel", "error",
                        "-y",
                        "-f", "rawvideo",
                        "-pix_fmt", "bgr24",
                        "-s", f"{w}x{h}",
                        "-r", str(self.fps),
                        "-i", "-",
                        "-an",
                        "-c:v", "libx264",
                        "-preset", "ultrafast",
                        "-tune", "zerolatency",
                        "-pix_fmt", "yuv420p",
                        "-g", str(self.fps*2),
                        "-keyint_min", str(self.fps*2),
                        "-bf", "0",
                        "-maxrate", "1M",
                        "-bufsize", "2M",
                        "-f", "flv",
                        self.url,
                    ]
                    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

                # 4. 写入数据
                try:
                    proc.stdin.write(frame.tobytes())
                except BrokenPipeError:
                    break

                # 5. 限速
                next_time += frame_interval
                sleep_time = next_time - time.time()
                if sleep_time > 0: time.sleep(sleep_time)
                else: next_time = time.time()

        finally:
            self._is_running = False
            cap.release()
            if proc and proc.stdin:
                proc.stdin.close()
                proc.wait()

import msvcrt # Windows 自带，用于实时检测键盘

if __name__ == "__main__":
    URL = "rtmp://127.0.0.1:1935/cam"
    FFMPEG = "D:/CodeSoftware/VisualStudioCode/VsCodeProject/info3180-vuejs-flask-starter/app/Cam/ffmpeg/bin/ffmpeg.exe"
    
    streamer = CamStream(url=URL, ffmpeg_exe=FFMPEG)
    streamer.start()

    print("\n--- 键盘测试说明 ---")
    print("[1] 切换分辨率至 1280x720")
    print("[2] 切换分辨率至 640x480")
    print("[3] 开启自动曝光")
    print("[4] 曝光值 -1 (变暗)")
    print("[5] 曝光值 +1 (变亮)")
    print("[Q] 退出程序")
    print("--------------------\n")

    current_exposure = -2 # 初始手动曝光参考值

    try:
        while True:
            # 检测是否有按键按下
            if msvcrt.kbhit():
                key = msvcrt.getch().decode('utf-8').lower()

                if key == '1':
                    streamer.set_resolution(1280, 720)
                
                elif key == '2':
                    streamer.set_resolution(640, 480)

                elif key == '3':
                    streamer.set_exposure(0) # 自动
                    print("已切换为自动曝光")

                elif key == '4':
                    current_exposure -= 1
                    streamer.set_exposure(current_exposure)
                    print(f"当前手动曝光值: {current_exposure}")

                elif key == '5':
                    current_exposure += 1
                    streamer.set_exposure(current_exposure)
                    print(f"当前手动曝光值: {current_exposure}")

                elif key == 'q':
                    print("正在退出...")
                    break
            
            time.sleep(0.1) # 减少 CPU 占用

    except Exception as e:
        print(f"运行出错: {e}")
    finally:
        streamer.stop()