import cv2
import numpy as np
import json
import time
import threading
import shutil
import queue
from pathlib import Path
from app.utils import read_record_config

from inference.python_tensorrt.model import Model

#todo 解决潜在错误隐患 切片标志位的竞态条件 - 磁盘已满

class CamStream:
    """
    流处理工作线程（消费者）。

    1. 接收 CamManager 送来的原始帧
    2. 控制当前推流 FPS
    3. resize 到目标推流分辨率
    4. 根据 enable_infer 决定是否调用 model.inference(frame)
    5. 本地定时分段录制 MP4 视频（与推流尺寸、帧率一致）
    - 只会保存推流成功的视频帧 推流失败直接跳过
    - 修改分辨率和帧率都会重新保存新视频（曝光不会）
    - 如果保存失败（硬件原因or磁盘已满）触发60s冷却期 到期后尝试重启开始保存新视频
    - 采用jetson硬件支持的异步保存方式并压缩为H.264 不会阻塞CamStream的循环逻辑
    - 每次保存新视频前读取AIConfig.yaml的record.duration_min作为当前视频最大时长
    6. 使用 GStreamer + x264enc 软件编码推 RTMP

    """

    def __init__(
        self,
        name,
        url,
        width=1280,
        height=720,
        fps=15,
        enable_infer=False,
        enable_record=False, # 默认不保存推流视频
        ai_config_path=None,
        video_base_dir=None

    ):
        self.name = name
        self.url = url

        self.width = int(width)
        self.height = int(height)
        self.fps = max(1, int(fps))

        self.frame_queue = queue.Queue(maxsize=2)
        self._is_running = False
        self._thread = None

        self._need_writer_restart = True
        self.set_lock = threading.Lock()

        self.enable_infer = bool(enable_infer)
        self.ai_config_path = ai_config_path
        self.ai_model = None
        self.ai_lock = threading.RLock()
        
        self._enable_record = enable_record  # 默认启动推流时同步开启录制
        self._record_writer = None
        self._record_start_time = 0.0
        self._record_duration_limit = 600.0  # 单位：秒
        self._need_record_restart = True     # 启动时默认需要初始化录制器
        self._record_cooldown_until = 0.0    # 冷却期截止时间戳
        self._min_free_space_mb = 500        # 最少需要保留 500MB 磁盘空间
        self._record_file_path = None
        self._record_has_target = False

        self.video_base_dir = video_base_dir if video_base_dir else Path(__file__).parent.parent.parent.resolve()

    # =========================================================
    # GStreamer 推流相关
    # =========================================================

    def _suggest_bitrate_kbps(self, w, h, fps):
        """
        x264enc 的 bitrate 单位是 kbps。
        """
        pixels = int(w) * int(h)

        if pixels >= 2560 * 1440:
            return 15000
        elif pixels >= 1920 * 1080:
            return 12000
        elif pixels >= 1280 * 720:
            return 8000
        else:
            return 4000

    def _build_gst_pipeline(self, current_w, current_h, current_fps):
        """
        OpenCV VideoWriter 使用的 GStreamer pipeline。

        输入是 OpenCV BGR frame。
        编码器使用 x264enc 软件编码。
        """
        current_w = int(current_w)
        current_h = int(current_h)
        current_fps = max(1, int(current_fps))

        bitrate_kbps = self._suggest_bitrate_kbps(
            current_w,
            current_h,
            current_fps,
        )
        hw_bitrate = bitrate_kbps * 1000

        pipeline = (
            f"appsrc is-live=true block=false format=time do-timestamp=true "
            f"! video/x-raw,format=BGR,width={current_w},height={current_h},framerate={current_fps}/1 "
            f"! queue leaky=downstream max-size-buffers=2 "
            f"! videoconvert "
            f"! video/x-raw,format=I420 "
            f"! x264enc "
            f"bitrate={bitrate_kbps} "
            f"speed-preset=faster "
            f"tune=zerolatency "
            f"key-int-max={current_fps} "
            f"bframes=0 "
            f"byte-stream=false "
            f"! h264parse config-interval=1 "
            f"! flvmux streamable=true "
            f"! rtmpsink location={self.url} sync=false async=false"
        )

        return pipeline

    def _open_writer(self, current_w, current_h, current_fps):
        pipeline = self._build_gst_pipeline(
            current_w=current_w,
            current_h=current_h,
            current_fps=current_fps,
        )

        print(f"[{self.name}] GStreamer pipeline:")
        print(pipeline)

        writer = cv2.VideoWriter(
            pipeline,
            cv2.CAP_GSTREAMER,
            0,
            float(current_fps),
            (int(current_w), int(current_h)),
            True,
        )

        if not writer.isOpened():
            raise RuntimeError(
                f"[{self.name}] 无法打开 GStreamer VideoWriter。"
                f"请检查 x264enc / rtmpsink / flvmux / MediaMTX 是否正常。"
            )

        print(
            f"[{self.name}] GStreamer 已启动: "
            f"{current_w}x{current_h}@{current_fps}, url={self.url}"
        )

        return writer

    def _close_writer(self, writer):
        if writer is None:
            return

        try:
            writer.release()
        except Exception as e:
            print(f"[{self.name}] 释放 GStreamer writer 失败: {e}")
            
    def _close_record_writer(self):
        if self._record_writer is not None:
            try:
                self._record_writer.release() # 视频结束时必须调用 release() 进行 “收尾”
            except Exception as e:
                print(f"[{self.name}] 释放本地录制 writer 失败: {e}")
            self._record_writer = None
        self._write_record_metadata()
        self._record_file_path = None
        self._record_has_target = False

    def _write_record_metadata(self):
        if self._record_file_path is None:
            return

        try:
            metadata_path = self._record_file_path.with_suffix(".json")
            metadata = {
                "filename": self._record_file_path.name,
                "title": self._record_file_path.stem,
                "target": self.name,
                "start_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self._record_start_time)),
                "duration_sec": max(0, int(round(time.time() - self._record_start_time))),
                "has_target": bool(self._record_has_target),
            }
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[{self.name}] 写入视频元数据失败: {e}")
            
    def _open_record_writer(self, current_w, current_h, current_fps):
        """
        根据当前最新的配置，初始化本地视频录制对象
        """
        # 1. 检查是否在冷却期内
        if time.time() < self._record_cooldown_until:
            return
        
        self._close_record_writer()
        
        # 从 YAML 文件中实时动态加载录制截止时长
        duration_min = read_record_config(self.ai_config_path)
        self._record_duration_limit = duration_min * 60.0

        base_dir = self.video_base_dir
        video_dir = base_dir / "video" / self.name
        video_dir.mkdir(parents=True, exist_ok=True)
        
        # 磁盘余量检测
        total, used, free = shutil.disk_usage(str(video_dir))
        free_mb = free / (1024 * 1024)
        if free_mb < self._min_free_space_mb:
            print(f"[{self.name}] 警告：磁盘空间不足 (剩余 {free_mb:.2f}MB)。暂停录制 60 秒。")
            self._record_cooldown_until = time.time() + 60.0
            self._record_writer = None
            return

        # 构造 YYYYMMDD_HHMMSS 格式文件名
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        file_path = video_dir / f"{timestamp_str}.mkv"
        
        bitrate = self._suggest_bitrate_kbps(current_w, current_h, current_fps) * 1000
        gst_pipeline = (
            f"appsrc is-live=true block=false format=time do-timestamp=true " # 自动为每帧添加时间戳 确保Jetson编码器正常工作
            f"! video/x-raw,format=BGR,width={current_w},height={current_h},framerate={current_fps}/1 "
            f"! videorate " # videorate 强制对齐帧率
            f"! video/x-raw,framerate={current_fps}/1 "
            f"! queue leaky=downstream max-size-buffers={current_fps} " # 缓冲 1 秒的数据
            # ---------- 下面是异步操作 GStreamer底层自动开辟线程完成 ----------- #
            f"! videoconvert ! video/x-raw,format=I420 "
            f"! x264enc bitrate={int(bitrate/1000)} speed-preset=veryfast " # 替换为软件编码以解决无 nvv4l2h264enc 问题
            f"! h264parse "
            f"! matroskamux "
            f"! filesink location={file_path} sync=false async=false"
        )
        self._record_writer = cv2.VideoWriter(
            gst_pipeline,
            cv2.CAP_GSTREAMER,
            0,
            float(current_fps),
            (int(current_w), int(current_h)),
            True
        )

        if not self._record_writer.isOpened():
            print(f"[{self.name}] 警告：无法打开本地视频录制 Writer: {file_path} 60 秒冷却中")
            self._record_writer = None
            self._record_cooldown_until = time.time() + 60.0
            return

        self._record_start_time = time.time()
        self._record_file_path = file_path
        self._record_has_target = False
        # self._need_record_restart = False # 在 lock 中已经置为 False 这里不用再重置
        print(f"[{self.name}] 启动新分段本地录制: {file_path}, 分段时长: {duration_min} 分钟")

    # =========================================================
    # 前端控制接口
    # =========================================================

    def set_resolution(self, width, height):
        width = int(width)
        height = int(height)

        if width <= 0 or height <= 0:
            raise ValueError("width 和 height 必须大于 0")

        if width % 2 != 0 or height % 2 != 0:
            raise ValueError("H.264/I420 要求 width 和 height 必须是偶数")

        with self.set_lock:
            self.width = width
            self.height = height
            self._need_writer_restart = True
            self._need_record_restart = True  # 修改尺寸后本地录制必须立刻切片保存

        print(f"[{self.name}] 目标分辨率变更为: {self.width}x{self.height}")

    def set_fps(self, fps):
        fps = max(1, int(fps))

        with self.set_lock:
            self.fps = fps
            self._need_writer_restart = True
            self._need_record_restart = True  # 修改帧率后本地录制必须立刻切片保存

        print(f"[{self.name}] 目标推流帧率变更为: {self.fps}")

    def set_infer_enable(
        self,
        enable: bool,
        reload_when_enable: bool = True,
        release_when_disable: bool = True,
    ):
        enable = bool(enable)

        with self.ai_lock:
            old_enable = self.enable_infer
            self.enable_infer = enable

            if enable:
                print(f"[{self.name}] 前端请求开启 AI 推理")

                model = self._ensure_ai_model_locked()

                if reload_when_enable:
                    model.reload_config()
                    print(f"[{self.name}] AI 配置已重载，Python TensorRT 推理已重启")

                print(f"[{self.name}] AI 推理已开启")

            else:
                print(f"[{self.name}] 前端请求关闭 AI 推理")

                if release_when_disable:
                    self._close_ai_model_locked()
                    print(f"[{self.name}] AI 推理已关闭, Python TensorRT 推理已释放")
                else:
                    print(f"[{self.name}] AI 推理已关闭，但 Python TensorRT 推理保留")

            if old_enable != enable:
                print(f"[{self.name}] AI 推理状态变化: {old_enable} -> {enable}")

    def reload_ai_config(self):
        with self.ai_lock:
            if not self.enable_infer:
                print(f"[{self.name}] 当前未开启 AI 推理，跳过 reload_ai_config")
                return

            model = self._ensure_ai_model_locked()
            model.reload_config()
            print(f"[{self.name}] AI 配置已重载, Python TensorRT 推理已重启")

    # =========================================================
    # 队列与线程控制
    # =========================================================

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

        print(f"[CamStream[{self.name}]] GStreamer 推流消费者已启动: {self.url}")

    def stop(self):
        self._is_running = False

        if self._thread:
            self._thread.join()
            self._thread = None
            print(f"[{self.name}] 推流消费者已停止")

        self._close_ai_model()

    # =========================================================
    # AI 推理相关
    # =========================================================

    def _ensure_ai_model_locked(self):
        if self.ai_model is not None:
            return self.ai_model

        if self.ai_config_path is None:
            raise RuntimeError(
                f"[{self.name}] enable_infer=True，但没有传入 ai_config_path"
            )

        config_path = Path(self.ai_config_path).resolve()

        if not config_path.exists():
            raise FileNotFoundError(f"[{self.name}] AIConfig.yaml 不存在: {config_path}")

        print(f"[{self.name}] 正在初始化 AI 模型: {config_path}")

        self.ai_model = Model(config=str(config_path))

        print(f"[{self.name}] AI 模型初始化完成")

        return self.ai_model

    def _close_ai_model_locked(self):
        if self.ai_model is None:
            return

        try:
            self.ai_model.close()
        except Exception as e:
            print(f"[{self.name}] 关闭 AI 模型失败: {e}")

        self.ai_model = None

    def _close_ai_model(self):
        with self.ai_lock:
            self._close_ai_model_locked()

    def _run_inference_if_enabled(self, frame):
        with self.ai_lock:
            enable_infer = self.enable_infer

        if not enable_infer:
            return frame

        try:
            with self.ai_lock:
                model = self._ensure_ai_model_locked()
                result = model.inference(frame)
                if self._enable_record and getattr(model, "last_detection_flag", False):
                    self._record_has_target = True

            if result is None:
                print(f"[{self.name}] AI 推理返回 None，使用原始帧")
                return frame

            if result.shape[:2] != frame.shape[:2]:
                result = cv2.resize(result, (frame.shape[1], frame.shape[0]))

            return result

        except Exception as e:
            print(f"[{self.name}] AI 推理失败，使用原始帧继续推流: {e}")
            return frame

    # =========================================================
    # 图像格式整理
    # =========================================================

    def _prepare_frame_for_writer(self, frame, current_w, current_h):
        if frame is None:
            return None

        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        if frame.ndim != 3 or frame.shape[2] != 3:
            print(f"[{self.name}] 非法帧格式: shape={frame.shape}")
            return None

        if frame.shape[:2] != (current_h, current_w):
            print(
                f"[{self.name}] 推理后尺寸不一致: "
                f"{frame.shape[1]}x{frame.shape[0]} -> {current_w}x{current_h}"
            )
            frame = cv2.resize(frame, (current_w, current_h))

        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)

        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)

        return frame

    # =========================================================
    # 主工作线程
    # =========================================================

    def _worker_task(self):
        writer = None
        next_time = time.time()

        while self._is_running:
            try:
                raw_frame = self.frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            with self.set_lock:
                current_w = int(self.width)
                current_h = int(self.height)
                current_fps = max(1, int(self.fps))
                need_restart = self._need_writer_restart
                need_rec_restart = self._need_record_restart
                # 在锁内直接重置，防止执行 _open_record_writer 期间的新指令被覆盖
                # 导致写入视频前后两帧的尺寸不一致 程序崩溃
                if need_rec_restart:
                    self._need_record_restart = False 

            # 1. 分辨率/FPS 变化时，先重启 GStreamer writer
            if need_restart or writer is None or not writer.isOpened():
                self._close_writer(writer)
                writer = None

                try:
                    writer = self._open_writer(
                        current_w=current_w,
                        current_h=current_h,
                        current_fps=current_fps,
                    )

                    with self.set_lock:
                        if (
                            self.width == current_w
                            and self.height == current_h
                            and self.fps == current_fps
                        ):
                            self._need_writer_restart = False

                    next_time = time.time()

                except Exception as e:
                    print(f"[{self.name}] 启动 GStreamer writer 失败: {e}")

                    with self.set_lock:
                        self._need_writer_restart = True

                    time.sleep(1.0)
                    continue
                
            # 2. 检查、切换或创建 本地录制 VideoWriter
            now = time.time()
            time_expired = False
            if self._record_writer is not None:
                # 判断当前分段录制时长是否到期
                time_expired = (now - self._record_start_time) >= self._record_duration_limit

            if self._enable_record and time.time() >= self._record_cooldown_until:
                # 需要写入新视频的条件
                # 1. 前端修改了 fps 或 分辨率
                # 2. CamStream类首次初始化
                # 3. 当前分段到期
                    if need_rec_restart or self._record_writer is None or time_expired:
                        try:
                            self._open_record_writer(current_w, current_h, current_fps)
                        except Exception as e:
                            print(f"[{self.name}] 维护本地录制写入器异常: {e}")
                            self._close_record_writer()
                            self._record_cooldown_until = time.time() + 60.0

            # 3. FPS 控制
            now = time.time()
            frame_duration = 1.0 / current_fps

            if now < next_time:
                continue

            if now > next_time + frame_duration * 2:
                next_time = now + frame_duration
            else:
                next_time += frame_duration

            # 4. resize 到当前推流目标尺寸
            raw_h, raw_w = raw_frame.shape[:2]

            if current_w != raw_w or current_h != raw_h:
                frame = cv2.resize(raw_frame, (current_w, current_h))
            else:
                frame = raw_frame

            # 5. AI 推理
            frame = self._run_inference_if_enabled(frame)

            # 6. 写入前格式检查
            frame = self._prepare_frame_for_writer(
                frame,
                current_w=current_w,
                current_h=current_h,
            )

            if frame is None:
                continue

            # 7. 写入 GStreamer
            try:
                if writer is None or not writer.isOpened():
                    print(f"[{self.name}] GStreamer writer 已关闭，准备重启")
                    with self.set_lock:
                        self._need_writer_restart = True
                    continue

                writer.write(frame)

            except Exception as e:
                print(f"[{self.name}] 写入 GStreamer 异常: {e}")

                with self.set_lock:
                    self._need_writer_restart = True

                self._close_writer(writer)
                writer = None
                continue # 当前frame推流失败直接进入下一次循环 不再写入视频文件
                
            # 8. 写入本地录制文件 (每推流一帧，保存一帧)
            if self._enable_record and self._record_writer is not None:
                # 如果当前由于磁盘已满或record_writer打开失败而在60s冷却期内直接跳过
                if time.time() < self._record_cooldown_until: 
                    continue
                try:
                    self._record_writer.write(frame) # 通过GStreamer pipeline进行异步写入
                except Exception as e:
                    print(f"[{self.name}] 写入本地视频文件异常: {e}")
                    # 发生异常时，除了请求重启，必须主动释放损坏的句柄并触发冷却
                    self._close_record_writer()
                    self._record_cooldown_until = time.time() + 60.0
                    with self.set_lock:
                        self._need_record_restart = True

        self._close_writer(writer)
        self._close_record_writer()
        print(f"[{self.name}] GStreamer worker 退出")
