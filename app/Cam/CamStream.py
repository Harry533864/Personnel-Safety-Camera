import cv2
import numpy as np
import json
import time
import threading
import shutil
from pathlib import Path
from app.utils import read_record_config

from inference.python_tensorrt.model import Model


class CamStream:
    """
    最小改动版：
    1. CamManager 仍然负责采集。
    2. CamStream 内部分成两个线程：
       - _infer_task：尽可能快地处理最新帧，只做 AI 推理。
       - _worker_task：按推流 FPS 取最新推理结果，负责推流和录制。
    3. 只保留最新帧，不处理积压旧帧。
    4. 软件编码 x264 仍保留，但不会直接卡住 AI 推理线程。
    """

    def __init__(
        self,
        name,
        url,
        width=1280,
        height=720,
        fps=15,
        enable_infer=False,
        enable_record=False,
        ai_config_path=None,
        video_base_dir=None,
    ):
        self.name = name
        self.url = url

        self.width = int(width)
        self.height = int(height)
        self.fps = max(1, int(fps))

        self._is_running = False
        self._thread = None          # 推流/录制线程
        self._infer_thread = None    # AI 推理线程

        self._need_writer_restart = True
        self.set_lock = threading.Lock()

        self.enable_infer = bool(enable_infer)
        self.ai_config_path = ai_config_path
        self.ai_model = None
        self.ai_lock = threading.RLock()

        # 只保存最新帧，避免旧帧积压
        self.frame_lock = threading.Lock()
        self.latest_raw_frame = None
        self.latest_infer_frame = None
        self.latest_infer_time = 0.0

        # 统计 AI 推理 FPS
        self._infer_frame_count = 0
        self._infer_stat_start = time.perf_counter()

        self._enable_record = bool(enable_record)
        self._record_writer = None
        self._record_start_time = 0.0
        self._record_duration_limit = 600.0
        self._need_record_restart = True
        self._record_cooldown_until = 0.0
        self._min_free_space_mb = 500
        self._record_file_path = None
        self._record_has_target = False

        self.video_base_dir = (
            video_base_dir
            if video_base_dir
            else Path(__file__).parent.parent.parent.resolve()
        )

        self._record_frame_count = 0
        self._write_frame_count = 0
        self._put_frame_count = 0

    # =========================================================
    # GStreamer 推流相关
    # =========================================================

    def _suggest_bitrate_kbps(self, w, h, fps):
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
        仍然使用 x264 软件编码。
        为降低 CPU 压力，建议使用 ultrafast。
        """
        current_w = int(current_w)
        current_h = int(current_h)
        current_fps = max(1, int(current_fps))

        bitrate_kbps = self._suggest_bitrate_kbps(
            current_w,
            current_h,
            current_fps,
        )

        pipeline = (
            f"appsrc is-live=true block=false format=time do-timestamp=true "
            f"! video/x-raw,format=BGR,width={current_w},height={current_h},framerate={current_fps}/1 "
            f"! queue leaky=downstream max-size-buffers=2 "
            f"! videoconvert "
            f"! video/x-raw,format=I420 "
            f"! x264enc "
            f"bitrate={bitrate_kbps} "
            f"speed-preset=ultrafast "
            f"tune=zerolatency "
            f"key-int-max={current_fps} "
            f"bframes=0 "
            f"threads=2 "
            f"sliced-threads=true "
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

    # =========================================================
    # 本地录制相关
    # =========================================================

    def _close_record_writer(self):
        if self._record_writer is not None:
            try:
                self._record_writer.release()
                print(f"[{self.name}] 结束录制分段 录制帧数 {self._record_frame_count}")
                print(f"[{self.name}] 结束录制分段 视频流推送帧数 {self._write_frame_count}")
                print(f"[{self.name}] 结束录制分段 CamManager视频流写入帧数 {self._put_frame_count}")
            except Exception as e:
                print(f"[{self.name}] 释放本地录制 writer 失败: {e}")

            self._record_writer = None
            self._record_frame_count = 0
            self._write_frame_count = 0
            self._put_frame_count = 0

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
                "start_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%S",
                    time.localtime(self._record_start_time),
                ),
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
        if time.time() < self._record_cooldown_until:
            return

        self._close_record_writer()

        duration_min = read_record_config(self.ai_config_path)
        self._record_duration_limit = duration_min * 60.0

        base_dir = self.video_base_dir
        video_dir = base_dir / "video" / self.name
        video_dir.mkdir(parents=True, exist_ok=True)

        total, used, free = shutil.disk_usage(str(video_dir))
        free_mb = free / (1024 * 1024)

        if free_mb < self._min_free_space_mb:
            print(f"[{self.name}] 警告：磁盘空间不足，剩余 {free_mb:.2f}MB。暂停录制 60 秒。")
            self._record_cooldown_until = time.time() + 60.0
            self._record_writer = None
            return

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        file_path = video_dir / f"{timestamp_str}.mkv"

        bitrate = self._suggest_bitrate_kbps(current_w, current_h, current_fps) * 1000

        # 软件编码场景下尽量使用 ultrafast，降低对 AI 推理线程的 CPU 争抢
        gst_pipeline = (
            f"appsrc is-live=true block=false format=time do-timestamp=true "
            f"! video/x-raw,format=BGR,width={current_w},height={current_h},framerate={current_fps}/1 "
            f"! queue leaky=downstream max-size-buffers={current_fps} "
            f"! videoconvert "
            f"! video/x-raw,format=I420 "
            f"! x264enc "
            f"bitrate={int(bitrate / 1000)} "
            f"speed-preset=ultrafast "
            f"tune=zerolatency "
            f"bframes=0 "
            f"threads=2 "
            f"sliced-threads=true "
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
            True,
        )

        if not self._record_writer.isOpened():
            print(f"[{self.name}] 警告：无法打开本地视频录制 Writer: {file_path}，60 秒冷却中")
            self._record_writer = None
            self._record_cooldown_until = time.time() + 60.0
            return

        self._record_start_time = time.time()
        self._record_file_path = file_path
        self._record_has_target = False

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
            self._need_record_restart = True

        print(f"[{self.name}] 目标分辨率变更为: {self.width}x{self.height}")

    def set_fps(self, fps):
        fps = max(1, int(fps))

        with self.set_lock:
            self.fps = fps
            self._need_writer_restart = True
            self._need_record_restart = True

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
        """
        最小改动关键点：
        不再使用 maxsize=10 的队列，只保留最新帧。
        这样 AI 推理永远处理最新画面，不会处理历史积压帧。
        """
        if not self._is_running:
            return

        if frame is None:
            return

        with self.frame_lock:
            self.latest_raw_frame = frame

        self._put_frame_count += 1

    def start(self):
        if self._is_running:
            return

        self._is_running = True

        # AI 推理线程
        self._infer_thread = threading.Thread(
            target=self._infer_task,
            daemon=True,
            name=f"CamStreamInfer-{self.name}",
        )
        self._infer_thread.start()

        # 推流/录制线程
        self._thread = threading.Thread(
            target=self._worker_task,
            daemon=True,
            name=f"CamStreamWriter-{self.name}",
        )
        self._thread.start()

        print(f"[CamStream[{self.name}]] 推理线程 + GStreamer 推流线程已启动: {self.url}")

    def stop(self):
        self._is_running = False

        if self._infer_thread:
            self._infer_thread.join()
            self._infer_thread = None
            print(f"[{self.name}] AI 推理线程已停止")

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

    def _infer_task(self):
        """
        独立 AI 推理线程。
        只做：
        1. 取最新 raw_frame
        2. model.inference()
        3. 写入 latest_infer_frame

        这样 writer.write() 和 record_writer.write() 不会阻塞 AI 推理。
        """
        while self._is_running:
            with self.frame_lock:
                frame = self.latest_raw_frame
                self.latest_raw_frame = None

            if frame is None:
                time.sleep(0.001)
                continue

            # 只在取模型对象时加锁，不把整段推理包在 ai_lock 里
            with self.ai_lock:
                enable_infer = self.enable_infer
                model = None
                if enable_infer:
                    model = self._ensure_ai_model_locked()

            if not enable_infer or model is None:
                result = frame
            else:
                try:
                    infer_start = time.perf_counter()
                    result = model.inference(frame)
                    infer_end = time.perf_counter()

                    if result is None:
                        result = frame

                    if self._enable_record and getattr(model, "last_detection_flag", False):
                        self._record_has_target = True

                    self._infer_frame_count += 1

                    # 打印推理时间和 FPS 统计，每 30 帧打印一次
                    # if self._infer_frame_count % 30 == 0:
                    #     now = time.perf_counter()
                    #     elapsed = now - self._infer_stat_start
                    #     if elapsed > 0:
                    #         infer_fps = 30 / elapsed
                    #         infer_latency_ms = (infer_end - infer_start) * 1000
                    #         print(
                    #             f"[{self.name}] AI inference FPS: {infer_fps:.2f}, "
                    #             f"last inference latency: {infer_latency_ms:.2f} ms"
                    #         )
                    #     self._infer_stat_start = now

                except Exception as e:
                    print(f"[{self.name}] AI 推理失败，使用原始帧继续推流: {e}")
                    result = frame

            with self.frame_lock:
                self.latest_infer_frame = result
                self.latest_infer_time = time.time()

        print(f"[{self.name}] AI 推理线程退出")

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
            frame = cv2.resize(frame, (current_w, current_h))

        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)

        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)

        return frame

    # =========================================================
    # 主推流/录制线程
    # =========================================================

    def _worker_task(self):
        writer = None
        next_time = time.time()

        while self._is_running:
            with self.set_lock:
                current_w = int(self.width)
                current_h = int(self.height)
                current_fps = max(1, int(self.fps))
                need_restart = self._need_writer_restart
                need_rec_restart = self._need_record_restart

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

            # 2. 检查、切换或创建本地录制 VideoWriter
            now = time.time()
            time_expired = False

            if self._record_writer is not None:
                time_expired = (
                    now - self._record_start_time
                ) >= self._record_duration_limit

            if self._enable_record and time.time() >= self._record_cooldown_until:
                if need_rec_restart or self._record_writer is None or time_expired:
                    try:
                        self._open_record_writer(current_w, current_h, current_fps)
                    except Exception as e:
                        print(f"[{self.name}] 维护本地录制写入器异常: {e}")
                        self._close_record_writer()
                        self._record_cooldown_until = time.time() + 60.0

            # 3. 推流 FPS 控制
            now = time.time()
            frame_duration = 1.0 / current_fps

            if now < (next_time - frame_duration * 0.25):
                time.sleep(0.001)
                continue

            if now > next_time + frame_duration * 2:
                next_time = now + frame_duration
            else:
                next_time += frame_duration

            # 4. 取最新 AI 推理结果
            with self.frame_lock:
                frame = self.latest_infer_frame

            if frame is None:
                time.sleep(0.001)
                continue

            # 5. 写入前格式检查、resize 到推流尺寸
            frame = self._prepare_frame_for_writer(
                frame,
                current_w=current_w,
                current_h=current_h,
            )

            if frame is None:
                continue

            # 6. 写入 GStreamer 推流
            try:
                if writer is None or not writer.isOpened():
                    print(f"[{self.name}] GStreamer writer 已关闭，准备重启")
                    with self.set_lock:
                        self._need_writer_restart = True
                    continue

                writer.write(frame)
                self._write_frame_count += 1

            except Exception as e:
                print(f"[{self.name}] 写入 GStreamer 异常: {e}")

                with self.set_lock:
                    self._need_writer_restart = True

                self._close_writer(writer)
                writer = None
                continue

            # 7. 写入本地录制文件
            if self._enable_record and self._record_writer is not None:
                if time.time() < self._record_cooldown_until:
                    continue

                try:
                    self._record_writer.write(frame)
                    self._record_frame_count += 1
                except Exception as e:
                    print(f"[{self.name}] 写入本地视频文件异常: {e}")
                    self._close_record_writer()
                    self._record_cooldown_until = time.time() + 60.0
                    with self.set_lock:
                        self._need_record_restart = True

        self._close_writer(writer)
        self._close_record_writer()
        print(f"[{self.name}] GStreamer worker 退出")