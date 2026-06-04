from __future__ import annotations

import logging
import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.Cam.CamManager import CamManager
from app.Cam.CamStream import CamStream
from app.runtime_paths import AI_CONFIG_PATH, MODEL_FILE_PATH, VIDEO_BASE_PATH
from app.services.config_service import ai_config_service
from app.utils import should_enable_stream_ai, to_bool


logger = logging.getLogger(__name__)

URL_LOW = os.environ.get("CAM_LOW_RTMP_URL", "rtmp://127.0.0.1:1935/cam_low")
URL_HIGH = os.environ.get("CAM_HIGH_RTMP_URL", "rtmp://127.0.0.1:1935/cam_high")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _camera_id() -> int | str:
    raw = os.environ.get("CAMERA_DEVICE", os.environ.get("CAM_CAMERA_ID", "0"))
    return int(raw) if str(raw).isdigit() else raw


def _read_ai_startup_state() -> tuple[bool, str]:
    try:
        cfg = ai_config_service.read()
    except FileNotFoundError:
        logger.warning("AI config missing at %s; startup inference disabled", AI_CONFIG_PATH)
        return False, "high"

    model_cfg = cfg.get("model", {})
    enable = to_bool(model_cfg.get("detect_enable", False))
    target = str(model_cfg.get("infer_target", "high")).lower()
    if target not in {"high", "low", "all"}:
        logger.warning("Invalid infer_target=%s; using high", target)
        target = "high"
    return enable, target


ORI_WIDTH = _env_int("CAMERA_WIDTH", 1920)
ORI_HEIGHT = _env_int("CAMERA_HEIGHT", 1080)
ORI_FPS = _env_int("CAMERA_FPS", 60)

cam_manager = CamManager(
    camera_id=_camera_id(),
    width=ORI_WIDTH,
    height=ORI_HEIGHT,
    fps=ORI_FPS,
)

AI_INFER_ENABLE, AI_INFER_TARGET = _read_ai_startup_state()

stream_high = CamStream(
    name="cam_high",
    url=URL_HIGH,
    width=1920,
    height=1080,
    fps=60,
    enable_infer=should_enable_stream_ai("cam_high", AI_INFER_ENABLE, AI_INFER_TARGET),
    ai_config_path=str(AI_CONFIG_PATH),
    enable_record=True,
    video_base_dir=VIDEO_BASE_PATH,
)

stream_low = CamStream(
    name="cam_low",
    url=URL_LOW,
    width=640,
    height=480,
    fps=15,
    enable_infer=should_enable_stream_ai("cam_low", AI_INFER_ENABLE, AI_INFER_TARGET),
    ai_config_path=str(AI_CONFIG_PATH),
    enable_record=False,
    video_base_dir=VIDEO_BASE_PATH,
)

cam_manager.add_worker(stream_high)


def get_target_streams(target: str = "high") -> list[CamStream]:
    target = str(target or "high").lower()
    if target == "high":
        return [stream_high]
    if target == "low":
        return [stream_low]
    if target == "all":
        return [stream_high, stream_low]
    raise ValueError("target must be high, low, or all")


def set_infer_enable(enable: bool, target: str = "high") -> list[str]:
    changed = []
    for stream in get_target_streams(target):
        stream.set_infer_enable(
            enable=enable,
            reload_when_enable=True,
            release_when_disable=True,
        )
        changed.append(stream.name)
    return changed


def sync_infer_enable_from_config(cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = cfg if cfg is not None else ai_config_service.read()
    model_cfg = cfg.get("model", {})
    detect_enable = to_bool(model_cfg.get("detect_enable", False))
    target = str(model_cfg.get("infer_target", "high")).lower()
    if target not in {"high", "low", "all"}:
        raise ValueError("infer_target must be high, low, or all")

    enabled_stream_names = {
        stream.name for stream in get_target_streams(target)
    } if detect_enable else set()

    changed = []
    for stream in [stream_high, stream_low]:
        old_enable = bool(getattr(stream, "enable_infer", False))
        new_enable = stream.name in enabled_stream_names

        if old_enable != new_enable:
            stream.set_infer_enable(
                enable=new_enable,
                reload_when_enable=True,
                release_when_disable=True,
            )
            changed.append({
                "name": stream.name,
                "old_enable": old_enable,
                "new_enable": new_enable,
                "action": "enable" if new_enable else "disable",
            })
        elif new_enable:
            stream.reload_ai_config()
            changed.append({
                "name": stream.name,
                "old_enable": old_enable,
                "new_enable": new_enable,
                "action": "reload",
            })

    return changed


def reload_enabled_streams() -> list[str]:
    reloaded = []
    for stream in [stream_high, stream_low]:
        if getattr(stream, "enable_infer", False):
            stream.reload_ai_config()
            reloaded.append(stream.name)
    return reloaded


def start_runtime() -> None:
    cam_manager.start()


def stop_runtime() -> None:
    cam_manager.stop()


def maybe_start_runtime() -> None:
    if to_bool(os.environ.get("CAM_AUTO_START", "1")):
        start_runtime()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            pass
    return str(value)


def _safe_status(label: str, status_fn, fallback=None):
    try:
        return _json_safe(status_fn()), None
    except Exception as error:
        logger.exception("Failed to build runtime status for %s", label)
        return fallback or {}, {"target": label, "message": str(error)}


def build_runtime_status() -> dict[str, Any]:
    camera_status, camera_error = _safe_status("camera", cam_manager.get_status)
    high_status, high_error = _safe_status("cam_high", stream_high.get_status)
    low_status, low_error = _safe_status("cam_low", stream_low.get_status)
    status_errors = [
        error for error in (camera_error, high_error, low_error) if error is not None
    ]

    return {
        "paths": {
            "ai_config": str(AI_CONFIG_PATH),
            "model_dir": str(MODEL_FILE_PATH),
            "video_base_dir": str(VIDEO_BASE_PATH),
        },
        "camera": camera_status,
        "streams": [high_status, low_status],
        "status_errors": status_errors,
    }

