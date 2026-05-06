from pathlib import Path
import struct
import subprocess
import sys
import threading
import atexit

import cv2
import numpy as np
from ruamel.yaml import YAML


ROOT = Path(__file__).resolve().parent.parent



class Model:
    def __init__(self, config=f"{ROOT}/AIConfig.yaml"):
        self.config_path = Path(config).resolve()
        self.cfg = self._load_yaml(self.config_path)

        model_cfg = self.cfg.get("model", self.cfg)

        self.exe_path = self._resolve_path(
            model_cfg.get("exe_path", "build/camera_tensorrt_server")
        )

        self.engine_path = self._resolve_path(
            model_cfg.get("engine_path", "models/person.engine")
        )

        self.det_config_path = self._resolve_path(
            model_cfg.get("config_path", "configs/config.json")
        )

        self.roi_config_path = self._resolve_path(
            model_cfg.get("roi_config_path", "configs/roi_config.json")
        )

        self.prestart_mode = bool(model_cfg.get("prestart_mode", False))
        self.settle_single_frame = bool(model_cfg.get("settle_single_frame", False))
        self.jpeg_quality = int(model_cfg.get("jpeg_quality", 95))

        self.proc = None
        self.lock = threading.Lock()

        self._check_files()
        self.proc = self._start_cpp_server()

        atexit.register(self.close)

    def inference(self, frame):
        """
        输入:
            frame: OpenCV 读取到的一帧图像，np.ndarray，BGR 格式

        输出:
            result: C++ 推理并绘图后的图像，np.ndarray，BGR 格式
        """
        frame = self._check_frame(frame)

        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
        )

        if not ok:
            raise RuntimeError("Python 编码输入图像失败")

        input_bytes = encoded.tobytes()

        with self.lock:
            self._write_packet(input_bytes)
            output_bytes = self._read_packet()

        if not output_bytes:
            raise RuntimeError("C++ 返回空结果，可能是图像解码或推理失败")

        result = cv2.imdecode(
            np.frombuffer(output_bytes, dtype=np.uint8),
            cv2.IMREAD_COLOR
        )

        if result is None:
            raise RuntimeError("Python 解码 C++ 返回图像失败")

        return result

    def close(self):
        if self.proc is None:
            return

        try:
            if self.proc.poll() is None and self.proc.stdin:
                # 发送长度 0，通知 C++ 服务端正常退出
                self.proc.stdin.write(struct.pack("<I", 0))
                self.proc.stdin.flush()
                self.proc.stdin.close()
        except Exception:
            pass

        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()

        self.proc = None

    def _start_cpp_server(self):
        cmd = [
            str(self.exe_path),
            str(self.engine_path),
            str(self.det_config_path),
            str(self.roi_config_path),
        ]

        if self.prestart_mode:
            cmd.append("--prestart")

        if self.settle_single_frame:
            cmd.append("--settle")

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0
        )

        threading.Thread(
            target=self._read_stderr_loop,
            args=(proc,),
            daemon=True
        ).start()

        return proc

    def _write_packet(self, data):
        if self.proc is None:
            raise RuntimeError("C++ 进程未启动")

        if self.proc.poll() is not None:
            raise RuntimeError(f"C++ 进程已经退出，returncode={self.proc.returncode}")

        if self.proc.stdin is None:
            raise RuntimeError("C++ stdin 不可用")

        size = len(data)
        header = struct.pack("<I", size)

        try:
            self.proc.stdin.write(header)
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except BrokenPipeError:
            raise RuntimeError("C++ stdin 已断开，写入失败")

    def _read_packet(self):
        header = self._read_exact(4)

        if len(header) != 4:
            raise RuntimeError("读取 C++ 返回长度失败")

        size = struct.unpack("<I", header)[0]

        if size == 0:
            return b""

        return self._read_exact(size)

    def _read_exact(self, size):
        if self.proc is None:
            raise RuntimeError("C++ 进程未启动")

        if self.proc.stdout is None:
            raise RuntimeError("C++ stdout 不可用")

        data = bytearray()

        while len(data) < size:
            chunk = self.proc.stdout.read(size - len(data))

            if not chunk:
                raise RuntimeError("C++ stdout 已断开，读取失败")

            data.extend(chunk)

        return bytes(data)

    def _read_stderr_loop(self, proc):
        if proc.stderr is None:
            return

        for line in iter(proc.stderr.readline, b""):
            msg = line.decode("utf-8", errors="ignore").rstrip()
            if msg:
                print(f"[cpp] {msg}", file=sys.stderr)

    def _check_frame(self, frame):
        if frame is None:
            raise ValueError("输入 frame 为 None")

        if not isinstance(frame, np.ndarray):
            raise TypeError(f"输入必须是 np.ndarray，但收到: {type(frame)}")

        if frame.size == 0:
            raise ValueError("输入 frame 为空图像")

        if frame.dtype != np.uint8:
            frame = np.clip(frame, 0, 255).astype(np.uint8)

        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(
                f"期望输入 HxWx3 BGR 图像，但收到 shape={frame.shape}"
            )

        return np.ascontiguousarray(frame)

    def _check_files(self):
        if not self.exe_path.exists():
            raise FileNotFoundError(f"C++ 可执行文件不存在: {self.exe_path}")

        if not self.engine_path.exists():
            raise FileNotFoundError(f"TensorRT engine 不存在: {self.engine_path}")

        if not self.det_config_path.exists():
            raise FileNotFoundError(f"检测配置文件不存在: {self.det_config_path}")

        if not self.roi_config_path.exists():
            raise FileNotFoundError(f"ROI 配置文件不存在: {self.roi_config_path}")

    def _load_yaml(self, path):
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        yaml = YAML(typ="safe")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.load(f)

        return data or {}

    def _resolve_path(self, path):
        path = Path(path)

        if path.is_absolute():
            return path

        return (ROOT / path).resolve()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __del__(self):
        self.close()


def _parse_video_source(source):
    """
    将 YAML 中的 source 统一转为可以在 cv2.VideoCapture 中使用的值。
    - 整数 → "/dev/video{source}"
    - 纯数字字符串 → "/dev/video{int(source)}"
    - 其他字符串(RTSP/视频文件/图片路径)→ 原样返回
    """
    if isinstance(source, int):
        return f"/dev/video{source}"
    if isinstance(source, str) and source.isdigit():
        return f"/dev/video{int(source)}"
    return source


# def _parse_video_source(source):
#     """
#     YAML 里如果写 source: 0，读取到的是 int，可以直接打开摄像头。
#     如果写 source: "0"，这里也会转成 int 0。
#     如果写 RTSP / 视频路径 / 图片路径，则保持字符串。
#     """
#     if isinstance(source, int):
#         return source

#     if isinstance(source, str) and source.isdigit():
#         return int(source)

#     return source


def run_image_test(model, image_path):
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"测试图片不存在: {image_path}")

    frame = cv2.imread(str(image_path))

    if frame is None:
        raise RuntimeError(f"无法读取测试图片: {image_path}")

    result = model.inference(frame)

    # cv2.imshow("C++ TensorRT Result", result)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()

    cv2.imwrite("test_result.jpg", result)
    print("测试结果已保存到 test_result.jpg")


def run_video_test(model, source, width=None, height=None, fps=None):
    source = _parse_video_source(source)

    cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频源: {source}")

    if width is not None:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))

    if height is not None:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))

    if fps is not None:
        cap.set(cv2.CAP_PROP_FPS, int(fps))

    frame_count = 0
    while True:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("读取图像失败或视频结束")
            break

        result = model.inference(frame)

        # 保存前几十帧测试
        if frame_count < 10: 
            cv2.imwrite(f"test_frame_{frame_count}.jpg", result)
            print(f"已保存 test_frame_{frame_count}.jpg")
        elif frame_count == 10:
            print("测试帧保存完毕，退出测试")
            break
            
        frame_count += 1

        # cv2.imshow("C++ TensorRT Result", result)

        # key = cv2.waitKey(1) & 0xFF

        # if key == 27 or key == ord("q"):
        #     break

    cap.release()
    cv2.destroyAllWindows()


def main():
    with Model() as model:
        test_cfg = model.cfg.get("test", {})

        source = test_cfg.get("source", 0)
        width = test_cfg.get("width", None)
        height = test_cfg.get("height", None)
        fps = test_cfg.get("fps", None)

        source_path = Path(str(source))

        image_suffixes = {
            ".jpg", ".jpeg", ".png", ".bmp", ".webp"
        }

        if isinstance(source, str) and source_path.suffix.lower() in image_suffixes:
            run_image_test(model, source)
        else:
            run_video_test(
                model=model,
                source=source,
                width=width,
                height=height,
                fps=fps
            )


if __name__ == "__main__":
    main()