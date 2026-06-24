import cv2
import numpy as np
import time
import threading
import logging
from pathlib import Path
from app.Cam.inference_worker import InferenceWorker
from app.Cam.stream_publisher import StreamPublisher
from app.Cam.stream_recorder import StreamRecorder
from app.Cam.fps_meter import FpsMeter


class CamStream:
    """
    CamManager 负责采集，InferenceWorker 负责推理，
    CamStream 只调度推流和录制，避免把所有运行职责揉在一个类里。
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
        self.logger = logging.getLogger(f"{__name__}.{name}")
        self.publisher = StreamPublisher(name=name, url=url)

        self.width = int(width)
        self.height = int(height)
        self.fps = max(1, int(fps))

        self._is_running = False
        self._thread = None          # 推流/录制线程

        self._need_writer_restart = True
        self.set_lock = threading.Lock()
        self.ai_config_path = ai_config_path

        self.video_base_dir = (
            Path(video_base_dir).expanduser().resolve()
            if video_base_dir
            else Path(__file__).parent.parent.parent.resolve()
        )
        self.recorder = StreamRecorder(
            name=self.name,
            ai_config_path=self.ai_config_path,
            video_base_dir=self.video_base_dir,
            enabled=enable_record,
            bitrate_fn=self._suggest_bitrate_kbps,
        )
        self.inference = InferenceWorker(
            name=self.name,
            ai_config_path=self.ai_config_path,
            enabled=enable_infer,
            on_detection=self._mark_record_target,
        )

        self._write_frame_count = 0
        self._put_frame_count = 0
        self._received_fps = FpsMeter()
        self._written_fps = FpsMeter()
        self._mjpeg_fps = FpsMeter()

        self.status_lock = threading.Lock()
        self.last_write_success_at = 0.0
        self.last_writer_error = None
        self.writer_opened = False

    def _format_time(self, timestamp):
        if not timestamp:
            return None
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(timestamp))

    @property
    def enable_infer(self):
        return self.inference.enabled

    def _mark_record_target(self):
        if self.recorder.enabled:
            self.recorder.mark_target()

    def get_status(self):
        with self.set_lock:
            width = self.width
            height = self.height
            fps = self.fps
            need_writer_restart = self._need_writer_restart

        infer_status = self.inference.status()
        record_status = self.recorder.status()
        with self.status_lock:
            status = {
                "name": self.name,
                "url": self.url,
                "width": width,
                "height": height,
                "fps": fps,
                "actual_received_fps": self._received_fps.fps(),
                "actual_written_fps": self._written_fps.fps(),
                "actual_mjpeg_fps": self._mjpeg_fps.fps(),
                "actual_stream_fps": (
                    self._written_fps.fps()
                    if self.writer_opened
                    else self._mjpeg_fps.fps()
                ),
                "running": self._is_running,
                "writer_thread_alive": bool(self._thread and self._thread.is_alive()),
                "infer_thread_alive": infer_status["thread_alive"],
                "writer_opened": self.writer_opened,
                "need_writer_restart": need_writer_restart,
                "enable_infer": infer_status["enable_infer"],
                "model_loaded": infer_status["model_loaded"],
                "enable_record": record_status["enabled"],
                "recording": record_status["recording"],
                "record_file": record_status["file"],
                "has_raw_frame": infer_status["has_raw_frame"],
                "has_stream_frame": infer_status["has_stream_frame"],
                "has_infer_frame": infer_status["has_infer_frame"],
                "latest_infer_frame_at": infer_status["latest_infer_frame_at"],
                "last_raw_frame_at": infer_status["last_raw_frame_at"],
                "last_infer_success_at": infer_status["last_infer_success_at"],
                "last_write_success_at": self._format_time(
                    self.last_write_success_at
                ),
                "last_infer_latency_ms": infer_status["last_infer_latency_ms"],
                "last_infer_error": infer_status["last_infer_error"],
                "last_writer_error": self.last_writer_error,
                "frames_received": self._put_frame_count,
                "frames_written": self._write_frame_count,
                "frames_inferred": infer_status["frames_inferred"],
                "actual_infer_fps": infer_status["actual_infer_fps"],
                "frames_recorded": record_status["frames_recorded"],
                "record_last_error": record_status["last_error"],
                "record_encoder": record_status["encoder"],
                "publisher_last_error": self.publisher.last_error,
                "publisher_encoder": self.publisher.last_encoder,
                "publisher_pipeline": self.publisher.last_pipeline,
            }

        return status

    def _record_stats(self):
        return {
            "frames_received": self._put_frame_count,
            "frames_written": self._write_frame_count,
        }

    # =========================================================
    # GStreamer 推流相关
    # =========================================================

    def _suggest_bitrate_kbps(self, w, h, fps):
        return self.publisher.suggest_bitrate_kbps(w, h, fps)

    def _build_gst_pipeline(self, current_w, current_h, current_fps):
        return self.publisher.build_pipeline(current_w, current_h, current_fps)

    def _open_writer(self, current_w, current_h, current_fps):
        return self.publisher.open_writer(current_w, current_h, current_fps)

    def _close_writer(self, writer):
        self.publisher.close_writer(writer)

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
            self.recorder.request_restart()

        self.logger.info("Target resolution changed: %sx%s", self.width, self.height)

    def set_fps(self, fps):
        fps = max(1, int(fps))

        with self.set_lock:
            self.fps = fps
            self._need_writer_restart = True
            self.recorder.request_restart()

        self.logger.info("Target stream FPS changed: %s", self.fps)

    def set_infer_enable(
        self,
        enable: bool,
        reload_when_enable: bool = True,
        release_when_disable: bool = True,
    ):
        self.inference.set_enabled(
            enable=enable,
            reload_when_enable=reload_when_enable,
            release_when_disable=release_when_disable,
        )

    def reload_ai_config(self):
        self.inference.reload_config()

    def get_overlay_state(self, max_age_sec=1.0):
        return self.inference.overlay_state(max_age_sec=max_age_sec)

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

        if self.inference.put_frame(frame):
            self._put_frame_count += 1
            self._received_fps.mark()

    def mark_mjpeg_frame(self):
        self._mjpeg_fps.mark()

    def start(self):
        if self._is_running:
            return

        self._is_running = True

        self.inference.start()

        # 推流/录制线程
        self._thread = threading.Thread(
            target=self._worker_task,
            daemon=True,
            name=f"CamStreamWriter-{self.name}",
        )
        self._thread.start()

        self.logger.info("Stream writer thread started: %s", self.url)

    def stop(self):
        self._is_running = False

        self.inference.stop()

        if self._thread:
            self._thread.join()
            self._thread = None
            self.logger.info("Stream writer thread stopped")


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
            self.logger.warning("Invalid frame shape: %s", frame.shape)
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

            publisher_unavailable = self.publisher.unavailable_reason()
            if publisher_unavailable:
                self._close_writer(writer)
                writer = None
                with self.status_lock:
                    self.writer_opened = False
                    self.last_writer_error = publisher_unavailable
                with self.set_lock:
                    self._need_writer_restart = False

            # 1. 分辨率/FPS 变化时，先重启 GStreamer writer
            if (
                not publisher_unavailable
                and (need_restart or writer is None or not writer.isOpened())
            ):
                self._close_writer(writer)
                writer = None
                with self.status_lock:
                    self.writer_opened = False

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
                    with self.status_lock:
                        self.writer_opened = True
                        self.last_writer_error = None

                except Exception as e:
                    self.logger.exception("Failed to start GStreamer writer")
                    with self.status_lock:
                        self.writer_opened = False
                        self.last_writer_error = str(e)

                    with self.set_lock:
                        self._need_writer_restart = True

                    time.sleep(1.0)
                    continue

            # 2. 检查、切换或创建本地录制 VideoWriter
            self.recorder.maintain(
                current_w,
                current_h,
                current_fps,
                self._record_stats(),
            )

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
            frame = self.inference.get_frame()

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
                if publisher_unavailable:
                    self.recorder.write(frame, self._record_stats())
                    continue

                if writer is None or not writer.isOpened():
                    self.logger.warning("GStreamer writer closed; restarting")
                    with self.status_lock:
                        self.writer_opened = False
                        self.last_writer_error = "writer closed"
                    with self.set_lock:
                        self._need_writer_restart = True
                    continue

                writer.write(frame)
                self._write_frame_count += 1
                self._written_fps.mark()
                with self.status_lock:
                    self.writer_opened = True
                    self.last_write_success_at = time.time()
                    self.last_writer_error = None

            except Exception as e:
                self.logger.exception("Failed to write GStreamer frame")
                with self.status_lock:
                    self.writer_opened = False
                    self.last_writer_error = str(e)

                with self.set_lock:
                    self._need_writer_restart = True

                self._close_writer(writer)
                writer = None
                continue

            # 7. 写入本地录制文件
            self.recorder.write(frame, self._record_stats())

        self._close_writer(writer)
        with self.status_lock:
            self.writer_opened = False
        self.recorder.close(self._record_stats())
        self.logger.info("GStreamer worker exited")
