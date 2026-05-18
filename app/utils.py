import os
from pathlib import Path
from ruamel.yaml import YAML


def read_yaml(file_path=None):
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {file_path}")

    yaml = YAML(typ="safe")

    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.load(f) or {}


def write_yaml(data, file_path=None):
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = file_path.with_suffix(".yaml.tmp")

    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True

    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

    os.replace(tmp_path, file_path)


def to_bool(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value != 0

    if isinstance(value, str):
        return value.lower() in ["true", "1", "yes", "on"]

    return bool(value)



def read_ai_startup_state(ai_config_path):
    """
    从 AIConfig.yaml 读取启动时的 AI 推理开关。
    """
    try:
        cfg = read_yaml(ai_config_path)
    except FileNotFoundError:
        print(f"[Startup] 配置文件不存在: {ai_config_path}, 默认关闭 AI 推理")
        return False, "high"

    model_cfg = cfg.get("model", {})

    enable = to_bool(model_cfg.get("detect_enable", False))
    target = str(model_cfg.get("infer_target", "high")).lower()

    if target not in ["high", "low", "all"]:
        print(f"[Startup] infer_target={target} 非法，默认使用 high")
        target = "high"

    print(f"[Startup] AI 推理配置: detect_enable={enable}, infer_target={target}")

    return enable, target


def should_enable_stream_ai(stream_name, enable, target):
    """
    判断某一路流启动时是否开启 AI 推理。
    """
    if not enable:
        return False

    if target == "all":
        return True

    if target == "high" and stream_name == "cam_high":
        return True

    if target == "low" and stream_name == "cam_low":
        return True

    return False


def normalize_roi(roi, index):
    """
    将前端 ROI 转换成 C++ 可用格式。

    注意：
    前端传回来的坐标已经是归一化坐标，因此这里不再做归一化处理。

    仅支持 polygon 格式：

    {
        "polygon": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]]
    }
    """
    if not isinstance(roi, dict):
        raise TypeError(f"rois[{index}] 必须是 object")

    polygon = roi.get("polygon")

    if polygon is None:
        raise ValueError(f"rois[{index}] 缺少 polygon")

    if not isinstance(polygon, list) or len(polygon) < 3:
        raise ValueError(f"rois[{index}].polygon 至少需要 3 个点")

    # 只检查格式，不修改坐标值
    checked_polygon = []
    for point_idx, point in enumerate(polygon):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(
                f"rois[{index}].polygon[{point_idx}] 必须是 [x, y]"
            )

        px = float(point[0])
        py = float(point[1])

        checked_polygon.append([px, py])

    return {
        "roi_id": str(roi.get("roi_id", roi.get("id", f"hazard_{index + 1}"))),
        "name": roi.get("name", f"ROI{index + 1}"),
        "enabled": to_bool(roi.get("enabled", True)),
        "roi_type": roi.get("roi_type", "forbidden_zone"),
        "judge_method": roi.get("judge_method", "overlap"),

        # 明确告诉 C++，这是归一化坐标
        "coordinate_mode": "normalized",

        # 前端传回来的归一化 polygon，原样保存
        "polygon": checked_polygon,

        "overlap_thres": float(roi.get("overlap_thres", 0.2)),
        "target": roi.get("target", "all"),
    }

