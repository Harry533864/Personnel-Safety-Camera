from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export YOLO .pt model to ONNX.")
    parser.add_argument("--model", default="inference/models/yolo11n.pt", help="Input .pt model path")
    parser.add_argument("--output", default="inference/models/yolo11n_person.onnx", help="Output ONNX path")
    parser.add_argument("--imgsz", type=int, default=640, help="Export image size")
    parser.add_argument("--opset", type=int, default=12, help="ONNX opset version")
    parser.add_argument("--dynamic", action="store_true", help="Export with dynamic input shape")
    parser.add_argument("--simplify", action="store_true", help="Simplify ONNX after export")
    parser.add_argument("--fp16", action="store_true", help="Convert exported ONNX weights to FP16")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise RuntimeError("ONNX 导出需要安装 ultralytics") from exc

    model_path = Path(args.model).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not model_path.exists():
        raise FileNotFoundError(f"模型文件不存在: {model_path}")

    model = YOLO(str(model_path))
    exported = model.export(
        format="onnx",
        imgsz=args.imgsz,
        opset=args.opset,
        dynamic=args.dynamic,
        simplify=args.simplify,
    )

    exported_path = Path(exported).resolve()
    if exported_path != output_path:
        output_path.write_bytes(exported_path.read_bytes())

    if args.fp16:
        try:
            import onnx
            from onnxconverter_common import float16
        except Exception as exc:
            raise RuntimeError(
                "FP16 ONNX conversion requires onnx and onnxconverter-common"
            ) from exc

        model_proto = onnx.load(str(output_path))
        model_proto = float16.convert_float_to_float16(model_proto, keep_io_types=True)
        onnx.save(model_proto, str(output_path))

    print(f"ONNX output: {output_path}")


if __name__ == "__main__":
    main()
