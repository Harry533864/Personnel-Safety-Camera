import cv2
import subprocess
import time

RTMP_URL = "rtmp://192.168.0.117:1935/cam" # 8554端口用于RTSP 1935用于RTMP
FFMPEG_EXE = "D:/CodeSoftware/VisualStudioCode/VsCodeProject/info3180-vuejs-flask-starter/app/Cam/ffmpeg/bin/ffmpeg.exe"   # 不在PATH就改成绝对路径

TARGET_WIDTH = 1080
TARGET_HEIGHT = 720
TARGET_FPS = 30

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)   # Windows 推荐
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
if not cap.isOpened():
    raise RuntimeError("无法打开摄像头")

cap.set(cv2.CAP_PROP_FRAME_WIDTH, TARGET_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, TARGET_HEIGHT)
cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)

ret, frame = cap.read()
if not ret:
    raise RuntimeError("无法读取摄像头首帧")

height, width = frame.shape[:2]
print(f"camera actual size: {width}x{height}")

ffmpeg_cmd = [
    FFMPEG_EXE,
    "-loglevel", "error",
    "-y",

    "-f", "rawvideo",
    "-pix_fmt", "bgr24",
    "-s", f"{width}x{height}",
    "-r", str(TARGET_FPS),
    "-i", "-",

    "-an",
    "-c:v", "libx264",
    "-preset", "ultrafast",
    "-tune", "zerolatency",
    "-pix_fmt", "yuv420p",

    "-g", str(TARGET_FPS),     # 关键帧间隔
    "-keyint_min", str(TARGET_FPS * 2),
    "-bf", "0",

    "-maxrate", "1M",
    "-bufsize", "500k",

    "-f", "flv", # rstp 时使用 "rtsp"
    # "-rtsp_transport", "tcp",
    RTMP_URL,
]

print("run:", " ".join(ffmpeg_cmd))
proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

frame_interval = 1.0 / TARGET_FPS
next_time = time.time()

try:
    # 首帧先送进去
    proc.stdin.write(frame.tobytes())

    while True:
        ret, frame = cap.read()
        if not ret:
            print("读取摄像头失败")
            break

        if proc.poll() is not None:
            print("FFmpeg 已退出")
            break

        proc.stdin.write(frame.tobytes())

        # 简单限速，尽量稳定推流节奏
        next_time += frame_interval
        sleep_time = next_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
            # 如果处理跟不上，重置节奏，避免延迟不断累积
            next_time = time.time()

except KeyboardInterrupt:
    pass
except BrokenPipeError:
    print("FFmpeg 管道断开")
finally:
    cap.release()
    if proc.stdin:
        proc.stdin.close()
    proc.wait()