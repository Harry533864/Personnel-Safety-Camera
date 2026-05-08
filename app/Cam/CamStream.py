import cv2
import numpy as np
import subprocess
import time
import threading
import queue
from pathlib import Path

from app.Cam.models import Model


class CamStream:
    """
    流处理工作线程（消费者）。

    负责：
    1. 接收 CamManager 送来的原始帧
    2. 控制当前推流 FPS
    3. resize 到目标推流分辨率
    4. 根据 enable_infer 决定是否调用 model.inference(frame)
    5. 将最终图像写入 FFmpeg 推流
    """

    def __init__(
        self,
        name,
        url,
        ffmpeg_exe="ffmpeg",
        width=1280,
        height=720,
        fps=15,

        # AI 推理相关参数
        enable_infer=False,
        ai_config_path=None,
    ):
        self.name = name
        self.url = url
        self.ffmpeg_exe = ffmpeg_exe

        self.width = int(width)
        self.height = int(height)
        self.fps = max(1, int(fps))

        self.frame_queue = queue.Queue(maxsize=2)
        self._is_running = False
        self._thread = None
        self._need_ffmpeg_restart = True

        self.set_lock = threading.Lock()

        # =========================
        # AI 推理相关
        # =========================
        self.enable_infer = bool(enable_infer)
        self.ai_config_path = ai_config_path
        self.ai_model = None
        self.ai_lock = threading.RLock()

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

            # H.264 编码
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-profile:v", "baseline",
            "-level", "3.1",
            "-g", str(current_fps),
            "-keyint_min", str(current_fps),
            "-sc_threshold", "0",
            "-bf", "0",
            "-b:v", "4000k",
            "-maxrate", "4000k",
            "-bufsize", "1000k",
            "-flush_packets", "1",
            "-f", "flv",
            "-flvflags", "no_duration_filesize",
            self.url,
        ]

    def set_resolution(self, width, height):
        with self.set_lock:
            self.width = int(width)
            self.height = int(height)
            self._need_ffmpeg_restart = True
            print(f"[{self.name}] 目标分辨率变更为: {self.width}x{self.height}")

    def set_fps(self, fps):
        with self.set_lock:
            self.fps = max(1, int(fps))
            self._need_ffmpeg_restart = True
            print(f"[{self.name}] 目标推流帧率变更为: {self.fps}")

    def set_infer_enable(
        self,
        enable: bool,
        reload_when_enable: bool = True,
        release_when_disable: bool = True,
    ):
        """
        前端控制是否开启 AI 推理。

        enable=True:
            开启推理。
            如果模型还没创建，会创建 Model, 并启动 C++ 推理子进程。
            如果 reload_when_enable=True, 会重新读取 AIConfig.yaml。

        enable=False:
            关闭推理。
            后续推流直接使用原始帧。
            如果 release_when_disable=True, 会关闭 C++ 推理子进程，释放资源。
        """
        enable = bool(enable)

        with self.ai_lock:
            old_enable = self.enable_infer
            self.enable_infer = enable

            if enable:
                print(f"[{self.name}] 前端请求开启 AI 推理")

                model = self._ensure_ai_model_locked()

                if reload_when_enable:
                    model.reload_config()
                    print(f"[{self.name}] AI 配置已重载，C++ 推理进程已重启")

                print(f"[{self.name}] AI 推理已开启")

            else:
                print(f"[{self.name}] 前端请求关闭 AI 推理")

                if release_when_disable:
                    self._close_ai_model_locked()
                    print(f"[{self.name}] AI 推理已关闭, C++ 推理进程已释放")
                else:
                    print(f"[{self.name}] AI 推理已关闭，但 C++ 推理进程保留")

            if old_enable != enable:
                print(f"[{self.name}] AI 推理状态变化: {old_enable} -> {enable}")

    def reload_ai_config(self):
        """
        后端更新 AIConfig.yaml 后调用。

        作用：
        1. 如果 AI 模型还没创建，则创建
        2. 如果 AI 模型已经创建，则调用 model.reload_config()
        3. model.reload_config() 内部会重新生成 runtime json 并重启 C++ 推理进程
        """
        with self.ai_lock:
            if not self.enable_infer:
                print(f"[{self.name}] 当前未开启 AI 推理，跳过 reload_ai_config")
                return

            model = self._ensure_ai_model_locked()
            model.reload_config()
            print(f"[{self.name}] AI 配置已重载, C++ 推理进程已重启")


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
            self._thread = None
            print(f"[{self.name}] 推流消费者已停止")

        self._close_ai_model()

    def _ensure_ai_model_locked(self):
        """
        调用这个函数前需要已经持有 self.ai_lock。
        """
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
        """
        调用前需要已经持有 self.ai_lock。
        """
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
        """
        对当前帧进行 AI 推理。

        输入:
            frame: BGR 图像，尺寸已经是当前推流分辨率

        输出:
            result: 推理后的 BGR 图像
        """
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
                self._need_ffmpeg_restart = False

            now = time.time()
            frame_duration = 1.0 / current_fps

            if now < next_time:
                continue

            if now > next_time + frame_duration * 2:
                next_time = now + frame_duration
            else:
                next_time += frame_duration

            # 1. 分辨率控制
            raw_h, raw_w = raw_frame.shape[:2]

            if current_w != raw_w or current_h != raw_h:
                frame = cv2.resize(raw_frame, (current_w, current_h))
            else:
                frame = raw_frame

            # 2. AI 推理
            # 注意：推理放在 resize 后，这样 C++ 返回图像尺寸就是推流尺寸。
            frame = self._run_inference_if_enabled(frame)

            # 3. FFmpeg 重启
            if need_restart:
                if proc:
                    try:
                        if proc.stdin:
                            proc.stdin.close()
                    except Exception:
                        pass

                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        proc.kill()

                ffmpeg_cmd = self._build_ffmpeg_cmd(
                    current_w=current_w,
                    current_h=current_h,
                    current_fps=current_fps,
                )

                proc = subprocess.Popen(
                    ffmpeg_cmd,
                    stdin=subprocess.PIPE,
                    bufsize=0,
                )

                print(
                    f"[{self.name}] FFmpeg 已启动: "
                    f"{current_w}x{current_h}@{current_fps}, url={self.url}"
                )

            # 4. 写入 FFmpeg
            try:
                if proc is None:
                    with self.set_lock:
                        self._need_ffmpeg_restart = True
                    continue

                if proc.poll() is not None:
                    print(f"[{self.name}] FFmpeg 进程已退出，准备重启...")
                    with self.set_lock:
                        self._need_ffmpeg_restart = True
                    continue

                if frame.dtype != np.uint8:
                    frame = np.clip(frame, 0, 255).astype(np.uint8)

                if not frame.flags["C_CONTIGUOUS"]:
                    frame = np.ascontiguousarray(frame)

                proc.stdin.write(frame.tobytes())

            except BrokenPipeError:
                print(f"[{self.name}] FFmpeg 管道断开，准备重连...")
                with self.set_lock:
                    self._need_ffmpeg_restart = True

            except (ValueError, OSError) as exc:
                print(f"[{self.name}] 写入 FFmpeg 异常: {exc}")
                with self.set_lock:
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