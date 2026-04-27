from ..CamManager import CamManager
from ..CamStream import CamStream
import time

def test_simple_stream():
    # 配置你的 FFmpeg 路径和 RTMP 推流地址
    FFMPEG_EXE = "D:/CodeSoftware/VisualStudioCode/VsCodeProject/info3180-vuejs-flask-starter/app/Cam/ffmpeg/bin/ffmpeg.exe"
    URL = "rtmp://127.0.0.1:1935/cam_test"
    
    # 1. 实例化 Manager（硬件层：1080P, 30fps）
    cam_manager = CamManager(camera_id=0, width=1920, height=1080, fps=30)
    
    # 2. 实例化 Worker（软件层：保持与硬件一致，不缩放、不降帧）
    stream_worker = CamStream(
        name="test_worker", 
        url=URL, 
        ffmpeg_exe=FFMPEG_EXE, 
        width=1920, 
        height=1080, 
        fps=30
    )
    
    # 3. 组装并启动
    cam_manager.add_worker(stream_worker)
    cam_manager.start()    # 再启动生产者开始供图
    
    try:
        # 保持主线程存活，观察推流情况
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n正在停止推流...")
    finally:
        # CamManager 的 stop 会一并调用所有 worker 的 stop
        cam_manager.stop()
        print("=== 测试结束 ===")
        
def test_multi_stream():
    # 请确保 FFmpeg 路径正确
    FFMPEG_EXE = "D:/CodeSoftware/VisualStudioCode/VsCodeProject/info3180-vuejs-flask-starter/app/Cam/ffmpeg/bin/ffmpeg.exe"
    
    # 定义两路独立的 RTMP 推流地址
    URL_HIGH = "rtmp://127.0.0.1:1935/cam_high"
    URL_LOW = "rtmp://127.0.0.1:1935/cam_low"
    
    # 1. 实例化 Manager（硬件生产者）
    # 必须以所有流中最高的需求规格进行初始化，这里取 1920x1080 @ 30fps
    cam_manager = CamManager(camera_id=0, width=1920, height=1080, fps=30)
    
    # 2. 实例化 Worker 1（高画质消费者：不缩放，不抽帧）
    stream_high = CamStream(
        name="cam_high", 
        url=URL_HIGH, 
        ffmpeg_exe=FFMPEG_EXE, 
        width=1280, 
        height=720, 
        fps=30
    )
    
    # 3. 实例化 Worker 2（低画质消费者：软件缩放至 720P，软件降帧至 15fps）
    stream_low = CamStream(
        name="cam_low", 
        url=URL_LOW, 
        ffmpeg_exe=FFMPEG_EXE, 
        width=320, 
        height=160, 
        fps=3
    )
    
    # 4. 组装订阅关系
    cam_manager.add_worker(stream_high)
    cam_manager.add_worker(stream_low)
    
    # 5. 启动线程
    # 最佳实践：先启动所有消费者监听队列，最后启动生产者开始供图
    cam_manager.start()
    
    try:
        # 保持主线程存活，防止程序立刻退出
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[主程序] 接收到退出信号(Ctrl+C)，正在安全停止推流与摄像头占用...")
    finally:
        # 只需要调用 Manager 的 stop，它内部会遍历调用所有 worker 的 stop
        cam_manager.stop()
        print("=== 多路推流测试结束 ===")
        
def test_exposure_stream():
    # 请确保 FFmpeg 路径正确
    FFMPEG_EXE = "D:/CodeSoftware/VisualStudioCode/VsCodeProject/info3180-vuejs-flask-starter/app/Cam/ffmpeg/bin/ffmpeg.exe"
    
    # 定义两路独立的 RTMP 推流地址
    URL_HIGH = "rtmp://127.0.0.1:1935/cam_high"
    URL_LOW = "rtmp://127.0.0.1:1935/cam_low"
    
    # 1. 实例化 Manager（硬件生产者）
    # 必须以所有流中最高的需求规格进行初始化，这里取 1920x1080 @ 30fps
    cam_manager = CamManager(camera_id=0, width=1920, height=1080, fps=30)
    
    # 2. 实例化 Worker 1（高画质消费者：不缩放，不抽帧）
    stream_high = CamStream(
        name="cam_high", 
        url=URL_HIGH, 
        ffmpeg_exe=FFMPEG_EXE, 
        width=1280, 
        height=720, 
        fps=30
    )
    
    # 3. 实例化 Worker 2（低画质消费者：软件缩放至 720P，软件降帧至 15fps）
    stream_low = CamStream(
        name="cam_low", 
        url=URL_LOW, 
        ffmpeg_exe=FFMPEG_EXE, 
        width=320, 
        height=160, 
        fps=15
    )
    
    # 4. 组装订阅关系
    cam_manager.add_worker(stream_high)
    cam_manager.add_worker(stream_low)
    
    # 5. 启动线程
    # 最佳实践：先启动所有消费者监听队列，最后启动生产者开始供图
    cam_manager.start()
    
    try:
        exposure_levels = [0, -3, -6, -9] # 曝光等级循环测试
        idx = 0
        while True:
            current_exp = exposure_levels[idx % len(exposure_levels)]
            cam_manager.set_exposure(current_exp)
            time.sleep(8)
            idx += 1
    except KeyboardInterrupt:
        print("[主程序] 接收到退出信号(Ctrl+C)，正在安全停止推流...")
    finally:
        cam_manager.stop()
        print("=== 曝光测试结束 ===")
        
if __name__ == "__main__":
    test_multi_stream()