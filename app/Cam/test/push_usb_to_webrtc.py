import cv2
import subprocess
import time

# ---------- 配置 ----------
MEDIAMTX_RTMP_URL = "rtmp://127.0.0.1:1935/stream"   # 若 MediaMTX 不在本机则改 IP
FFMPEG_EXE = "D:/CodeSoftware/VisualStudioCode/VsCodeProject/info3180-vuejs-flask-starter/app/Cam/ffmpeg/bin/ffmpeg.exe"

TARGET_WIDTH = 1280
TARGET_HEIGHT = 720
TARGET_FPS = 15

# ---------- 摄像头初始化 ----------
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    raise RuntimeError("无法打开摄像头")

cap.set(cv2.CAP_PROP_FRAME_WIDTH, TARGET_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, TARGET_HEIGHT)
cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)

ret, frame = cap.read()
if not ret:
    raise RuntimeError("无法读取摄像头首帧")
height, width = frame.shape[:2]
print(f"Camera actual size: {width}x{height}")

# ---------- FFmpeg 命令（RTMP 推流）----------
ffmpeg_cmd = [
    FFMPEG_EXE,
    "-loglevel", "error",
    "-y",

    "-f", "rawvideo",
    "-pix_fmt", "bgr24",
    "-s", f"{width}x{height}",
    "-r", str(TARGET_FPS),
    "-i", "-",

    "-an",                     # 无音频
    "-c:v", "libx264",
    "-preset", "ultrafast",
    "-tune", "zerolatency",
    "-pix_fmt", "yuv420p",

    # 关键帧间隔与 fps 匹配
    "-g", str(TARGET_FPS * 2),
    "-keyint_min", str(TARGET_FPS * 2),
    "-bf", "0",

    "-maxrate", "1M",
    "-bufsize", "2M",

    "-f", "flv",               # RTMP 容器
    MEDIAMTX_RTMP_URL
]

print("Run:", " ".join(ffmpeg_cmd))
proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

# ---------- 帧率控制 ----------
frame_interval = 1.0 / TARGET_FPS
next_time = time.time()

try:
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

        next_time += frame_interval
        sleep_time = next_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)
        else:
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