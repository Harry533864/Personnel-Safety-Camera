import re
from pathlib import Path

from app.utils import to_bool


MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
STREAM_TARGETS = {"high", "low", "all"}


def validate_model_name(value):
    name = str(value or "").strip()
    if not MODEL_NAME_PATTERN.fullmatch(name):
        raise ValueError("model_name 只能包含字母、数字、下划线、短横线，长度 1-64")
    return name


def resolve_model_dir(model_root, model_name):
    safe_name = validate_model_name(model_name)
    root = Path(model_root).resolve()
    model_dir = (root / safe_name).resolve()

    if model_dir != root and root not in model_dir.parents:
        raise ValueError("模型目录解析到非法路径")

    return safe_name, model_dir


def _ensure_dict(value, field):
    if not isinstance(value, dict):
        raise ValueError(f"{field} 必须是 object")
    return value


def _ensure_list(value, field):
    if not isinstance(value, list):
        raise ValueError(f"{field} 必须是数组")
    return value


def _number(value, field, min_value=None, max_value=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} 必须是数字")

    if min_value is not None and number < min_value:
        raise ValueError(f"{field} 不能小于 {min_value}")

    if max_value is not None and number > max_value:
        raise ValueError(f"{field} 不能大于 {max_value}")

    return number


def _int(value, field, min_value=None, max_value=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} 必须是整数")

    if min_value is not None and number < min_value:
        raise ValueError(f"{field} 不能小于 {min_value}")

    if max_value is not None and number > max_value:
        raise ValueError(f"{field} 不能大于 {max_value}")

    return number


def _validate_model_section(cfg):
    model_cfg = _ensure_dict(cfg.setdefault("model", {}), "model")

    if "infer_target" in model_cfg:
        target = str(model_cfg.get("infer_target", "high")).lower()
        if target not in STREAM_TARGETS:
            raise ValueError("model.infer_target 必须是 high、low 或 all")

    if "detect_enable" in model_cfg:
        to_bool(model_cfg["detect_enable"])

    if "model_name" in model_cfg and model_cfg["model_name"]:
        validate_model_name(model_cfg["model_name"])

    if "conf_thres" in model_cfg:
        _number(model_cfg["conf_thres"], "model.conf_thres", 0, 1)

    if "iou_thres" in model_cfg:
        _number(model_cfg["iou_thres"], "model.iou_thres", 0, 1)

    if "imgsz" in model_cfg:
        _int(model_cfg["imgsz"], "model.imgsz", 32, 4096)

    if "enter_frames" in model_cfg:
        _int(model_cfg["enter_frames"], "model.enter_frames", 0, 10000)

    if "exit_frames" in model_cfg:
        _int(model_cfg["exit_frames"], "model.exit_frames", 0, 10000)

    if "person_class_ids" in model_cfg:
        class_ids = _ensure_list(model_cfg["person_class_ids"], "model.person_class_ids")
        for index, class_id in enumerate(class_ids):
            _int(class_id, f"model.person_class_ids[{index}]", 0, 100000)

    if "person_class_names" in model_cfg:
        class_names = _ensure_list(
            model_cfg["person_class_names"],
            "model.person_class_names",
        )
        for index, class_name in enumerate(class_names):
            if not str(class_name or "").strip():
                raise ValueError(f"model.person_class_names[{index}] 不能为空")

    rois = model_cfg.get("rois", [])
    _ensure_list(rois, "model.rois")
    for roi_index, roi in enumerate(rois):
        _validate_roi(roi, roi_index)


def _validate_roi(roi, roi_index):
    roi = _ensure_dict(roi, f"model.rois[{roi_index}]")
    polygon = _ensure_list(roi.get("polygon"), f"model.rois[{roi_index}].polygon")
    if len(polygon) < 3:
        raise ValueError(f"model.rois[{roi_index}].polygon 至少需要 3 个点")

    for point_index, point in enumerate(polygon):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError(
                f"model.rois[{roi_index}].polygon[{point_index}] 必须是 [x, y]"
            )
        _number(point[0], f"model.rois[{roi_index}].polygon[{point_index}][0]", 0, 1)
        _number(point[1], f"model.rois[{roi_index}].polygon[{point_index}][1]", 0, 1)

    if "overlap_thres" in roi:
        _number(roi["overlap_thres"], f"model.rois[{roi_index}].overlap_thres", 0, 1)

    if "target" in roi:
        target = str(roi["target"]).lower()
        if target not in STREAM_TARGETS:
            raise ValueError(f"model.rois[{roi_index}].target 必须是 high、low 或 all")

    if "enabled" in roi:
        to_bool(roi["enabled"])


def _validate_model_names(cfg):
    model_names = cfg.get("model_names", [])
    _ensure_list(model_names, "model_names")
    for index, model_name in enumerate(model_names):
        validate_model_name(model_name)
        if str(model_name).strip() != model_name:
            raise ValueError(f"model_names[{index}] 不能包含首尾空格")


def _validate_exception_output(cfg):
    exception_output = cfg.get("exception_output")
    if exception_output is None:
        return

    exception_output = _ensure_dict(exception_output, "exception_output")
    pins = _ensure_list(exception_output.get("gpio", []), "exception_output.gpio")
    for index, pin in enumerate(pins):
        _int(pin, f"exception_output.gpio[{index}]", 1, 40)

    if "output_level" in exception_output:
        level = _int(exception_output["output_level"], "exception_output.output_level", 0, 1)
        if level not in {0, 1}:
            raise ValueError("exception_output.output_level 只能是 0 或 1")

    if "duration" in exception_output:
        _number(exception_output["duration"], "exception_output.duration", 0, 86400)


def _validate_record(cfg):
    record = cfg.get("record")
    if record is None:
        return

    record = _ensure_dict(record, "record")
    if "duration_min" in record:
        _number(record["duration_min"], "record.duration_min", 0.01, 1440)


def validate_ai_config(cfg):
    cfg = _ensure_dict(cfg, "AIConfig")
    _validate_model_section(cfg)
    _validate_model_names(cfg)
    _validate_exception_output(cfg)
    _validate_record(cfg)
    return cfg
