from pathlib import Path
import atexit
import json
import os
import struct
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
from ruamel.yaml import YAML


ROOT = Path(__file__).resolve().parent.parent


class Model:
    def __init__(self, config=f"{ROOT}/AIConfig.yaml"):
        self.config_path = Path(config).resolve()

        self.cfg = {}
        self.exe_path = None
        self.engine_path = None
        self.det_config_path = None
        self.roi_config_path = None

        self.prestart_mode = False
        self.settle_single_frame = False
        self.jpeg_quality = 95

        self.proc = None
        self.lock = threading.RLock()

        self._load_config_and_prepare_runtime()
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

    def reload_config(self):
        """
        前端修改 AIConfig.yaml 后调用这个函数。

        作用:
        1. 关闭旧 C++ 子进程
        2. 重新读取 AIConfig.yaml
        3. 重新生成 C++ runtime json
        4. 重新启动 C++ 子进程

        注意:
        当前 C++ 的 CameraTensorRTInfer 是启动时加载配置，
        所以修改 ROI / 阈值 / imgsz 后需要重启 C++ 子进程才能生效。
        """
        with self.lock:
            self.close()
            self._load_config_and_prepare_runtime()
            self._check_files()
            self.proc = self._start_cpp_server()

    def update_config(self, new_cfg):
        """
        可选接口:
        如果 Flask 后端收到前端传来的完整配置 dict，
        可以调用 model.update_config(new_cfg)。

        它会:
        1. 写回 AIConfig.yaml
        2. 重新加载配置
        3. 重启 C++ 推理进程
        """
        if not isinstance(new_cfg, dict):
            raise TypeError("new_cfg 必须是 dict")

        with self.lock:
            self._write_yaml_atomic(self.config_path, new_cfg)
            self.close()
            self._load_config_and_prepare_runtime()
            self._check_files()
            self.proc = self._start_cpp_server()

    def get_config(self):
        return self.cfg

    def close(self):
        with self.lock:
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

    def _load_config_and_prepare_runtime(self):
        self.cfg = self._load_yaml(self.config_path)

        model_cfg = self.cfg.get("model", self.cfg)

        self.exe_path = self._resolve_path(
            model_cfg.get("exe_path", "build/camera_tensorrt_server")
        )

        self.engine_path = self._resolve_path(
            model_cfg.get("engine_path", "weights/yolo11n_person.engine")
        )

        self.prestart_mode = bool(model_cfg.get("prestart_mode", False))
        self.settle_single_frame = bool(model_cfg.get("settle_single_frame", False))
        self.jpeg_quality = int(model_cfg.get("jpeg_quality", 95))

        runtime_dir = self._resolve_path(
            model_cfg.get("runtime_config_dir", "configs/runtime")
        )
        runtime_dir.mkdir(parents=True, exist_ok=True)

        self.det_config_path = runtime_dir / "config_runtime.json"
        self.roi_config_path = runtime_dir / "roi_config_runtime.json"

        self._export_cpp_runtime_json(model_cfg)

    def _export_cpp_runtime_json(self, model_cfg):
        """
        将 AIConfig.yaml 中的配置转换成 C++ 当前 LoadSafetyConfig 能读取的 JSON。

        C++ 当前会读取这些字段:
        - imgsz
        - conf_thres
        - iou_thres
        - enter_frames
        - exit_frames
        - rois
        """
        thresholds_cfg = model_cfg.get("thresholds", {})
        alarm_cfg = model_cfg.get("alarm", {})

        imgsz = int(model_cfg.get("imgsz", 640))

        conf_thres = float(
            model_cfg.get(
                "conf_thres",
                thresholds_cfg.get("conf_thres", 0.35)
            )
        )

        iou_thres = float(
            model_cfg.get(
                "iou_thres",
                thresholds_cfg.get("iou_thres", 0.45)
            )
        )

        enter_frames = int(
            model_cfg.get(
                "enter_frames",
                alarm_cfg.get("enter_frames", 3)
            )
        )

        exit_frames = int(
            model_cfg.get(
                "exit_frames",
                alarm_cfg.get("exit_frames", 5)
            )
        )

        rois = self._get_rois_from_config(model_cfg)

        runtime_config = {
            "version": str(model_cfg.get("version", "1.0")),
            "camera_id": model_cfg.get("camera_id", "cam_default"),
            "detect_enable": bool(model_cfg.get("detect_enable", True)),
            "model_name": model_cfg.get("model_name", "person_detector"),
            "backend": "tensorrt",

            # C++ 真正使用的 engine_path 来自命令行 argv[1]，
            # 这里保留只是为了 runtime json 可读、可追踪。
            "engine_path": str(self.engine_path),

            "imgsz": imgsz,
            "device": model_cfg.get("device", None),
            "person_class_ids": model_cfg.get("person_class_ids", [0]),

            "thresholds": {
                "conf_thres": conf_thres,
                "iou_thres": iou_thres
            },

            # 这里同时平铺一份，方便当前 roi_alarm.cpp 的正则解析。
            # 当前 C++ ExtractFloat 会全局搜索 "conf_thres" / "iou_thres"，
            # 所以放在 thresholds 里面也能被读到。
            "conf_thres": conf_thres,
            "iou_thres": iou_thres,

            "alarm": {
                "enter_frames": enter_frames,
                "exit_frames": exit_frames
            },

            # 同样平铺一份，方便当前 roi_alarm.cpp 的正则解析。
            "enter_frames": enter_frames,
            "exit_frames": exit_frames,

            "rois": rois
        }

        runtime_roi_config = {
            "version": str(model_cfg.get("version", "1.0")),
            "rois": rois
        }

        self._write_json_atomic(self.det_config_path, runtime_config)
        self._write_json_atomic(self.roi_config_path, runtime_roi_config)

    def _get_rois_from_config(self, model_cfg):
        """
        优先级:
        1. AIConfig.yaml 的 model.rois
        2. AIConfig.yaml 的 rois
        3. 兼容旧配置: model.roi_config_path 指向的 json
        """
        rois = model_cfg.get("rois", None)

        if rois is None:
            rois = self.cfg.get("rois", None)

        if rois:
            self._validate_rois(rois)
            return rois

        legacy_roi_config_path = model_cfg.get("roi_config_path", None)

        if legacy_roi_config_path:
            legacy_path = self._resolve_path(legacy_roi_config_path)

            if legacy_path.exists():
                legacy_cfg = self._load_json(legacy_path)
                rois = legacy_cfg.get("rois", [])

                if rois:
                    self._validate_rois(rois)
                    return rois

        raise ValueError(
            "没有找到 ROI 配置。请在 AIConfig.yaml 中配置 model.rois，"
            "或者提供旧版 roi_config_path。"
        )

    def _validate_rois(self, rois):
        if not isinstance(rois, list):
            raise TypeError("rois 必须是 list")

        if len(rois) == 0:
            raise ValueError("rois 不能为空")

        for idx, roi in enumerate(rois):
            if not isinstance(roi, dict):
                raise TypeError(f"rois[{idx}] 必须是 dict")

            required_keys = [
                "roi_id",
                "name",
                "enabled",
                "roi_type",
                "judge_method",
                "coordinate_mode",
                "polygon",
            ]

            for key in required_keys:
                if key not in roi:
                    raise ValueError(f"rois[{idx}] 缺少字段: {key}")

            polygon = roi.get("polygon", [])

            if not isinstance(polygon, list) or len(polygon) < 3:
                raise ValueError(f"rois[{idx}].polygon 至少需要 3 个点")

            for point_idx, point in enumerate(polygon):
                if (
                    not isinstance(point, list)
                    and not isinstance(point, tuple)
                ):
                    raise TypeError(
                        f"rois[{idx}].polygon[{point_idx}] 必须是 [x, y]"
                    )

                if len(point) != 2:
                    raise ValueError(
                        f"rois[{idx}].polygon[{point_idx}] 必须包含 2 个数值"
                    )

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
            raise FileNotFoundError(
                f"C++ runtime 检测配置不存在: {self.det_config_path}"
            )

        if not self.roi_config_path.exists():
            raise FileNotFoundError(
                f"C++ runtime ROI 配置不存在: {self.roi_config_path}"
            )

    def _load_yaml(self, path):
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        yaml = YAML(typ="safe")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.load(f)

        return data or {}

    def _load_json(self, path):
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"JSON 文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json_atomic(self, path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = path.with_suffix(path.suffix + ".tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        os.replace(tmp_path, path)

    def _write_yaml_atomic(self, path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = path.with_suffix(path.suffix + ".tmp")

        yaml = YAML()
        yaml.default_flow_style = False
        yaml.allow_unicode = True

        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

        os.replace(tmp_path, path)

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
        try:
            self.close()
        except Exception:
            pass



def main():
    CAMERA_ID = 0              # Jetson/Linux: /dev/video0
    WIDTH = 1280
    HEIGHT = 720
    FPS = 30

    WARMUP_FRAMES = 10         # 前 10 帧预热，不统计 FPS
    MAX_FRAMES = 300           # 测试 300 帧后退出；改成 0 表示一直跑
    REPORT_INTERVAL = 2.0      # 每隔 2 秒打印一次 FPS
    SHOW = False               # Jetson 无桌面环境建议 False
    SAVE_FIRST_FRAMES = 0      # 保存前 3 帧推理结果

    # =========================
    # 初始化 C++ 推理接口
    # =========================
    with Model() as model:
        # =========================
        # 打开摄像头
        # =========================
        source = f"/dev/video{CAMERA_ID}"

        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)

        if not cap.isOpened():
            raise RuntimeError(f"无法打开摄像头: {source}")

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FPS)

        # 尽量减少摄像头缓存，降低延迟
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = cap.get(cv2.CAP_PROP_FPS)

        print("=" * 80)
        print("摄像头实时推理 FPS 测试")
        print(f"camera      : {source}")
        print(f"request     : {WIDTH}x{HEIGHT}@{FPS}")
        print(f"actual      : {actual_w}x{actual_h}@{actual_fps:.2f}")
        print("=" * 80)

        frame_idx = 0
        valid_count = 0

        total_infer_time = 0.0
        total_e2e_time = 0.0

        window_count = 0
        window_infer_time = 0.0
        window_e2e_time = 0.0
        window_start = time.perf_counter()

        try:
            while True:
                e2e_start = time.perf_counter()

                ret, frame = cap.read()
                if not ret or frame is None:
                    print("读取摄像头失败")
                    continue

                # 参照推流代码：读取后统一 resize 到目标分辨率
                if frame.shape[1] != WIDTH or frame.shape[0] != HEIGHT:
                    frame = cv2.resize(frame, (WIDTH, HEIGHT))

                if frame.dtype != np.uint8:
                    frame = np.clip(frame, 0, 255).astype(np.uint8)

                if not frame.flags["C_CONTIGUOUS"]:
                    frame = np.ascontiguousarray(frame)

                # =========================
                # Python 调 C++ 推理
                # =========================
                infer_start = time.perf_counter()
                result = model.inference(frame)
                infer_end = time.perf_counter()

                e2e_end = time.perf_counter()

                frame_idx += 1

                if frame_idx <= SAVE_FIRST_FRAMES:
                    save_name = f"infer_test_frame_{frame_idx}.jpg"
                    cv2.imwrite(save_name, result)
                    print(f"已保存: {save_name}")

                # 预热帧不统计
                if frame_idx <= WARMUP_FRAMES:
                    print(f"\r预热中: {frame_idx}/{WARMUP_FRAMES}", end="", flush=True)
                    continue

                if frame_idx == WARMUP_FRAMES + 1:
                    print("\n预热结束，开始统计 FPS")

                infer_time = infer_end - infer_start
                e2e_time = e2e_end - e2e_start

                valid_count += 1

                total_infer_time += infer_time
                total_e2e_time += e2e_time

                window_count += 1
                window_infer_time += infer_time
                window_e2e_time += e2e_time

                if SHOW:
                    cv2.imshow("result", result)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q") or key == 27:
                        break

                now = time.perf_counter()

                if now - window_start >= REPORT_INTERVAL:
                    infer_fps = window_count / window_infer_time
                    total_fps = window_count / window_e2e_time
                    avg_infer_ms = window_infer_time / window_count * 1000
                    avg_total_ms = window_e2e_time / window_count * 1000

                    print(
                        f"[实时] "
                        f"frames={valid_count}, "
                        f"infer_fps={infer_fps:.2f}, "
                        f"total_fps={total_fps:.2f}, "
                        f"avg_infer={avg_infer_ms:.2f} ms, "
                        f"avg_total={avg_total_ms:.2f} ms"
                    )

                    window_count = 0
                    window_infer_time = 0.0
                    window_e2e_time = 0.0
                    window_start = now

                if MAX_FRAMES > 0 and valid_count >= MAX_FRAMES:
                    break

        except KeyboardInterrupt:
            print("\n用户退出")

        finally:
            cap.release()

            if SHOW:
                cv2.destroyAllWindows()

            if valid_count > 0:
                avg_infer_fps = valid_count / total_infer_time
                avg_total_fps = valid_count / total_e2e_time
                avg_infer_ms = total_infer_time / valid_count * 1000
                avg_total_ms = total_e2e_time / valid_count * 1000

                print("=" * 80)
                print("最终统计")
                print(f"统计帧数       : {valid_count}")
                print(f"平均 infer_fps : {avg_infer_fps:.2f}")
                print(f"平均 total_fps : {avg_total_fps:.2f}")
                print(f"平均 infer耗时 : {avg_infer_ms:.2f} ms")
                print(f"平均 total耗时 : {avg_total_ms:.2f} ms")
                print("=" * 80)


if __name__ == "__main__":
    main()