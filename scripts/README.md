# Inference And Model Conversion

当前目录只说明推理实现和模型转换脚本。默认推理实现为 Python TensorRT，C++ TensorRT 仅作为 legacy 备份保留。

## 当前结构

```text
camera/
├── inference/
│   ├── __init__.py
│   ├── configs/
│   │   ├── config.json                 # legacy 配置备份
│   │   └── roi_config.json             # legacy ROI 配置备份
│   ├── cpp_tensorrt/                   # legacy C++ TensorRT 实现
│   │   ├── CMakeLists.txt
│   │   ├── README.md
│   │   ├── include/
│   │   │   ├── common.hpp
│   │   │   ├── data_types.hpp
│   │   │   ├── inference.hpp
│   │   │   ├── roi_alarm.hpp
│   │   │   └── trt_detector.hpp
│   │   └── src/
│   │       ├── inference.cpp
│   │       ├── main.cpp
│   │       ├── roi_alarm.cpp
│   │       └── trt_detector.cpp
│   ├── models/
│   │   ├── yolo11n.pt                  # PyTorch 权重
│   │   ├── yolo11n_person.onnx         # ONNX 模型
│   │   └── yolo11n_person.engine       # TensorRT engine
│   ├── python_tensorrt/                # 默认 Python TensorRT 推理实现
│   │   ├── __init__.py
│   │   ├── model.py                    # Model 接口、配置加载、GPIO 报警
│   │   ├── runtime.py                  # TensorRT 执行、后处理、ROI 判断、画框
│   │   └── run_image.py                # 单图推理测试入口
│   └── test_img/
│       └── image.png                   # 单图测试图片
└── scripts/
    ├── export_onnx.py                  # 从 .pt 导出 ONNX
    └── build_tensorrt_engine.sh        # 在 Jetson 上生成 .engine
```

## Python TensorRT

Python TensorRT 默认入口：

```text
inference/python_tensorrt/model.py
```

实际 TensorRT 推理、YOLO 后处理、NMS、ROI 判断和画框在：

```text
inference/python_tensorrt/runtime.py
```

单图测试：

```bash
python -m inference.python_tensorrt.run_image \
  --config app/AIConfig.yaml \
  --image inference/test_img/image.png \
  --output outputs/python_tensorrt_result.jpg
```

运行时会根据 `app/AIConfig.yaml` 自动生成：

```text
inference/configs/runtime/config_runtime.json
inference/configs/runtime/roi_config_runtime.json
```

## 模型转换

从 PyTorch 权重导出 ONNX：

```bash
python scripts/export_onnx.py \
  --model inference/models/yolo11n.pt \
  --output inference/models/yolo11n_person.onnx \
  --imgsz 640
```

在 Jetson 上生成 TensorRT engine：

```bash
bash scripts/build_tensorrt_engine.sh \
  inference/models/yolo11n_person.onnx \
  inference/models/yolo11n_person.engine
```

TensorRT `.engine` 必须在最终运行的 Jetson 设备上生成，不能直接跨机器复用。

## 运行环境

已验证环境：

```text
Jetson Orin Nano
JetPack / L4T: R36.5.0
Python: 3.10
TensorRT Python: 10.3.0
Torch: 2.10.0 + CUDA 12.6
OpenCV: 4.8.0, with CUDA and GStreamer
```

环境要点：

- CUDA / TensorRT / cuDNN 使用 JetPack 自带版本。
- PyTorch 需要安装与 JetPack 匹配的 Jetson CUDA wheel。
- TensorRT Python binding 和 `torch.cuda` 必须可用。
- 不建议用普通 `opencv-python` 覆盖 Jetson 上支持 CUDA/GStreamer 的 OpenCV。

快速检查：

```bash
python - <<'PY'
import cv2
import torch
import tensorrt as trt

print("OpenCV:", cv2.__version__)
print("GStreamer:", "GStreamer:                   YES" in cv2.getBuildInformation())
print("Torch:", torch.__version__)
print("Torch CUDA:", torch.cuda.is_available())
print("TensorRT:", trt.__version__)
PY
```
