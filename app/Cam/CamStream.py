import cv2
import numpy as np
import time
import threading
import queue
from pathlib import Path

from inference.python_tensorrt.model import Model


class CamStream:
    """
    流处理工作线程（消费者）。

    1. 接收 CamManager 送来的原始帧
    2. 控制当前推流 FPS
    3. resize 到目标推流分辨率
    4. 根据 enable_infer 决定是否调用 model.inference(frame)
    5. 使用 GStreamer + x264enc 软件编码推 RTMP

    """

    def __init__(
        self,
        name,
        url,
        width=1280,
        height=720,
        fps=15,
        enable_infer=False,
        ai_config_path=None,
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

        print(f"[{self.name}] 目标分辨率变更为: {self.width}x{self.height}")

    def set_fps(self, fps):
        fps = max(1, int(fps))

        with self.set_lock:
            self.fps = fps
            self._need_writer_restart = True

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

            # 2. FPS 控制
            now = time.time()
            frame_duration = 1.0 / current_fps

            if now < next_time:
                continue

            if now > next_time + frame_duration * 2:
                next_time = now + frame_duration
            else:
                next_time += frame_duration

            # 3. resize 到当前推流目标尺寸
            raw_h, raw_w = raw_frame.shape[:2]

            if current_w != raw_w or current_h != raw_h:
                frame = cv2.resize(raw_frame, (current_w, current_h))
            else:
                frame = raw_frame

            # 4. AI 推理
            frame = self._run_inference_if_enabled(frame)

            # 5. 写入前格式检查
            frame = self._prepare_frame_for_writer(
                frame,
                current_w=current_w,
                current_h=current_h,
            )

            if frame is None:
                continue

            # 6. 写入 GStreamer
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

        self._close_writer(writer)
        print(f"[{self.name}] GStreamer worker 退出")
