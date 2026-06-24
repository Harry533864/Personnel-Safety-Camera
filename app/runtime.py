from __future__ import annotations

import logging
import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.Cam.CamManager import CamManager
from app.Cam.CamStream import CamStream
from app.camera_modes import normalize_camera_mode, sample_stream_fps
from app.runtime_paths import (
    AI_CONFIG_PATH,
    CAMERA_CONFIG_PATH,
    MODEL_FILE_PATH,
    VIDEO_BASE_PATH,
)
from app.services.camera_config_service import camera_config_service
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


def _env_choice(name: str, default: str, allowed: set[str]) -> str:
    raw = str(os.environ.get(name, default)).strip().lower()
    if raw not in allowed:
        logger.warning("Invalid %s=%s; using %s", name, raw, default)
        return default
    return raw


def _source_env(name: str, source: str, fallback: str | None = None) -> str | None:
    return os.environ.get(f"{source.upper()}_{name}", os.environ.get(fallback or name))


def _source_env_int(
    name: str,
    source: str,
    default: int,
    fallback: str | None = None,
) -> int:
    raw = _source_env(name, source, fallback)
    if raw is None or raw == "":
        return default
    return int(raw)


def _camera_id() -> int | str:
    raw = os.environ.get(
        f"{CAMERA_SOURCE.upper()}_CAMERA_DEVICE",
        os.environ.get("CAMERA_DEVICE", os.environ.get("CAM_CAMERA_ID", "0")),
    )
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


CAMERA_SOURCE = _env_choice("CAMERA_SOURCE", "usb", {"usb", "csi"})

if CAMERA_SOURCE == "csi":
    ORI_WIDTH = _source_env_int("CAMERA_WIDTH", "csi", 1920)
    ORI_HEIGHT = _source_env_int("CAMERA_HEIGHT", "csi", 1080)
    ORI_FPS = _source_env_int("CAMERA_FPS", "csi", 30)
else:
    ORI_WIDTH = _source_env_int("CAMERA_WIDTH", "usb", 1920)
    ORI_HEIGHT = _source_env_int("CAMERA_HEIGHT", "usb", 1080)
    ORI_FPS = _source_env_int("CAMERA_FPS", "usb", 60)

if CAMERA_SOURCE == "usb":
    _initial_mode = normalize_camera_mode(ORI_WIDTH, ORI_HEIGHT, ORI_FPS)
    ORI_WIDTH = _initial_mode["width"]
    ORI_HEIGHT = _initial_mode["height"]
    ORI_FPS = _initial_mode["fps"]

ENV_CAMERA_DEFAULTS = {
    "width": ORI_WIDTH,
    "height": ORI_HEIGHT,
    "fps": ORI_FPS,
    "exposure": int(os.environ.get("CAMERA_EXPOSURE", "0") or 0),
    "gain": int(os.environ.get("CAMERA_GAIN", "0") or 0),
    "white_balance": os.environ.get("CAMERA_WHITE_BALANCE", "continuous"),
    "power_line_frequency": os.environ.get("CAMERA_POWER_LINE_FREQUENCY", "1"),
    "target": "high",
}

try:
    STARTUP_CAMERA_CONFIG = camera_config_service.read(defaults=ENV_CAMERA_DEFAULTS)
except Exception:
    logger.exception(
        "Failed to read camera config from %s; using environment defaults",
        CAMERA_CONFIG_PATH,
    )
    STARTUP_CAMERA_CONFIG = camera_config_service.write(ENV_CAMERA_DEFAULTS)

ORI_WIDTH = int(STARTUP_CAMERA_CONFIG["width"])
ORI_HEIGHT = int(STARTUP_CAMERA_CONFIG["height"])
ORI_FPS = int(STARTUP_CAMERA_CONFIG["fps"])

logger.info(
    "Camera startup config path=%s width=%s height=%s fps=%s exposure=%s gain=%s "
    "white_balance=%s power_line_frequency=%s",
    CAMERA_CONFIG_PATH,
    STARTUP_CAMERA_CONFIG["width"],
    STARTUP_CAMERA_CONFIG["height"],
    STARTUP_CAMERA_CONFIG["fps"],
    STARTUP_CAMERA_CONFIG["exposure"],
    STARTUP_CAMERA_CONFIG["gain"],
    STARTUP_CAMERA_CONFIG["white_balance"],
    STARTUP_CAMERA_CONFIG["power_line_frequency"],
)

CSI_SENSOR_ID = _env_int("CSI_SENSOR_ID", 0)
CSI_FLIP_METHOD = _env_int("CSI_FLIP_METHOD", 0)
CSI_DIRECT_STREAM = to_bool(os.environ.get("CSI_DIRECT_STREAM", "0"))
CSI_DIRECT_RTMP_URL = os.environ.get("CSI_DIRECT_RTMP_URL", URL_HIGH)
STREAM_HIGH_PUBLISH = to_bool(
    os.environ.get(
        "STREAM_HIGH_PUBLISH",
        "0" if CAMERA_SOURCE == "csi" and CSI_DIRECT_STREAM else "1",
    )
)
STREAM_HIGH_RECORD = to_bool(
    os.environ.get(
        "STREAM_HIGH_RECORD",
        "0" if CAMERA_SOURCE == "csi" and CSI_DIRECT_STREAM else "1",
    )
)
STREAM_HIGH_WIDTH = _env_int("STREAM_HIGH_WIDTH", ORI_WIDTH)
STREAM_HIGH_HEIGHT = _env_int("STREAM_HIGH_HEIGHT", ORI_HEIGHT)
STREAM_HIGH_FPS = _env_int("STREAM_HIGH_FPS", ORI_FPS)
if CAMERA_SOURCE == "usb":
    _stream_high_mode = normalize_camera_mode(
        STREAM_HIGH_WIDTH,
        STREAM_HIGH_HEIGHT,
        STREAM_HIGH_FPS,
    )
    STREAM_HIGH_WIDTH = _stream_high_mode["width"]
    STREAM_HIGH_HEIGHT = _stream_high_mode["height"]
    STREAM_HIGH_FPS = _stream_high_mode["fps"]
    _stream_high_preview_mode = sample_stream_fps(
        STREAM_HIGH_WIDTH,
        STREAM_HIGH_HEIGHT,
        STREAM_HIGH_FPS,
    )
    STREAM_HIGH_WIDTH = _stream_high_preview_mode["width"]
    STREAM_HIGH_HEIGHT = _stream_high_preview_mode["height"]
    STREAM_HIGH_FPS = _stream_high_preview_mode["fps"]
CAMERA_FOURCC = _source_env("CAMERA_FOURCC", CAMERA_SOURCE) or "MJPG"
USB_CAMERA_DECODER = os.environ.get(
    "USB_CAMERA_DECODER",
    os.environ.get("CAMERA_DECODER", "auto"),
)

cam_manager = CamManager(
    camera_id=_camera_id(),
    camera_source=CAMERA_SOURCE,
    csi_sensor_id=CSI_SENSOR_ID,
    csi_flip_method=CSI_FLIP_METHOD,
    direct_stream_url=(
        CSI_DIRECT_RTMP_URL
        if CAMERA_SOURCE == "csi" and CSI_DIRECT_STREAM
        else None
    ),
    width=ORI_WIDTH,
    height=ORI_HEIGHT,
    fps=ORI_FPS,
    fourcc=CAMERA_FOURCC,
    usb_decoder=USB_CAMERA_DECODER,
)
cam_manager.set_exposure(int(STARTUP_CAMERA_CONFIG["exposure"]))
cam_manager.set_gain(int(STARTUP_CAMERA_CONFIG["gain"]))
cam_manager.set_white_balance(STARTUP_CAMERA_CONFIG["white_balance"])
cam_manager.set_power_line_frequency(STARTUP_CAMERA_CONFIG["power_line_frequency"])

AI_INFER_ENABLE, AI_INFER_TARGET = _read_ai_startup_state()

stream_high = CamStream(
    name="cam_high",
    url=URL_HIGH,
    width=STREAM_HIGH_WIDTH,
    height=STREAM_HIGH_HEIGHT,
    fps=STREAM_HIGH_FPS,
    enable_infer=should_enable_stream_ai("cam_high", AI_INFER_ENABLE, AI_INFER_TARGET),
    enable_publish=STREAM_HIGH_PUBLISH,
    ai_config_path=str(AI_CONFIG_PATH),
    enable_record=STREAM_HIGH_RECORD,
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


def get_detection_overlay(target: str = "high", max_age_sec: float = 1.0) -> dict[str, Any]:
    streams = get_target_streams(target)
    if not streams:
        raise ValueError("target must be high, low, or all")
    stream = streams[0]
    return stream.get_overlay_state(max_age_sec=max_age_sec)


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

