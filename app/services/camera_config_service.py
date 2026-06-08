from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime_paths import CAMERA_CONFIG_PATH
from app.utils import read_yaml, write_yaml


CAMERA_CONFIG_DEFAULTS: dict[str, Any] = {
    "resolution": "1920x1080",
    "width": 1920,
    "height": 1080,
    "fps": 60,
    "exposure": 0,
    "gain": 0.0,
    "white_balance": "continuous",
    "target": "high",
}


def normalize_white_balance(mode: Any) -> str:
    value = str(mode or "continuous").strip().lower()
    aliases = {
        "auto": "continuous",
        "on": "continuous",
        "true": "continuous",
        "1": "continuous",
        "continuous": "continuous",
        "once": "once",
        "single": "once",
        "off": "off",
        "manual": "off",
        "false": "off",
        "0": "off",
    }
    return aliases.get(value, "continuous")


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return int(default)
    return parsed if parsed > 0 else int(default)


def _non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(0, parsed)


def _non_negative_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return max(0.0, parsed)


def _extract_camera_block(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    camera = raw.get("camera")
    if isinstance(camera, dict):
        return camera
    return raw


def normalize_camera_config(
    raw: dict[str, Any] | None = None,
    defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = {
        **CAMERA_CONFIG_DEFAULTS,
        **(defaults or {}),
        **_extract_camera_block(raw),
    }

    width = _positive_int(merged.get("width"), CAMERA_CONFIG_DEFAULTS["width"])
    height = _positive_int(merged.get("height"), CAMERA_CONFIG_DEFAULTS["height"])
    fps = _positive_int(merged.get("fps"), CAMERA_CONFIG_DEFAULTS["fps"])

    resolution = str(merged.get("resolution") or "").strip().lower()
    if resolution not in {"max", "maximum", "auto_max"}:
        resolution = f"{width}x{height}"
    else:
        resolution = "max"

    target = str(merged.get("target") or "high").strip().lower()
    if target not in {"high", "low", "all"}:
        target = "high"

    return {
        "resolution": resolution,
        "width": width,
        "height": height,
        "fps": fps,
        "exposure": _non_negative_int(merged.get("exposure"), 0),
        "gain": _non_negative_float(merged.get("gain"), 0.0),
        "white_balance": normalize_white_balance(merged.get("white_balance")),
        "target": target,
    }


class CameraConfigService:
    """Thread-safe persistence for the last successful camera settings."""

    def __init__(self, path: str | Path = CAMERA_CONFIG_PATH) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def read(self, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            try:
                raw = read_yaml(self.path)
            except FileNotFoundError:
                raw = {}
            return normalize_camera_config(raw, defaults=defaults)

    def write(self, settings: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            normalized = normalize_camera_config(settings)
            write_yaml(
                {
                    "camera": normalized,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                file_path=self.path,
            )
            return normalized

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self.read()
            current.update(changes)
            return self.write(current)


camera_config_service = CameraConfigService()
