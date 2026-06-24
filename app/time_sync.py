from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any


_lock = threading.RLock()
_epoch_offset_sec = 0.0
_timezone_offset_min: int | None = None
_timezone_name = ""
_last_sync_monotonic: float | None = None
_last_client_epoch_sec: float | None = None
_last_client_iso = ""


def _parse_epoch_seconds(payload: dict[str, Any]) -> float:
    if "client_epoch_ms" in payload:
        return float(payload["client_epoch_ms"]) / 1000.0
    if "clientEpochMs" in payload:
        return float(payload["clientEpochMs"]) / 1000.0
    if "client_epoch_sec" in payload:
        return float(payload["client_epoch_sec"])
    if "clientEpochSec" in payload:
        return float(payload["clientEpochSec"])

    client_iso = str(payload.get("client_iso") or payload.get("clientIso") or "").strip()
    if client_iso:
        normalized = client_iso.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()

    raise ValueError("missing client time")


def _parse_timezone_offset_min(payload: dict[str, Any]) -> int | None:
    raw = payload.get("timezone_offset_min", payload.get("timezoneOffsetMin"))
    if raw is None:
        raw = payload.get("client_timezone_offset_min", payload.get("clientTimezoneOffsetMin"))
    if raw is None:
        return None
    return int(raw)


def sync_from_client(payload: dict[str, Any]) -> dict[str, Any]:
    global _epoch_offset_sec
    global _timezone_offset_min
    global _timezone_name
    global _last_sync_monotonic
    global _last_client_epoch_sec
    global _last_client_iso

    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    client_epoch_sec = _parse_epoch_seconds(payload)
    if client_epoch_sec < 1577836800 or client_epoch_sec > 4102444800:
        raise ValueError("client time is outside supported range")

    timezone_offset_min = _parse_timezone_offset_min(payload)
    timezone_name = str(
        payload.get("timezone")
        or payload.get("client_timezone")
        or payload.get("clientTimezone")
        or ""
    ).strip()

    with _lock:
        _epoch_offset_sec = client_epoch_sec - time.time()
        _timezone_offset_min = timezone_offset_min
        _timezone_name = timezone_name
        _last_sync_monotonic = time.monotonic()
        _last_client_epoch_sec = client_epoch_sec
        _last_client_iso = str(
            payload.get("client_iso") or payload.get("clientIso") or ""
        ).strip()
        return status()


def now_epoch() -> float:
    with _lock:
        return time.time() + _epoch_offset_sec


def is_synced(max_age_sec: float | None = None) -> bool:
    with _lock:
        if _last_sync_monotonic is None:
            return False
        if max_age_sec is None:
            return True
        return (time.monotonic() - _last_sync_monotonic) <= max_age_sec


def _client_local_datetime(epoch_sec: float | None = None) -> datetime:
    with _lock:
        epoch = now_epoch() if epoch_sec is None else float(epoch_sec)
        offset_min = _timezone_offset_min

    if offset_min is None:
        return datetime.fromtimestamp(epoch)
    return datetime.utcfromtimestamp(epoch - offset_min * 60)


def format_local(epoch_sec: float | None = None, fmt: str = "%Y-%m-%dT%H:%M:%S") -> str:
    return _client_local_datetime(epoch_sec).strftime(fmt)


def filename_timestamp(epoch_sec: float | None = None) -> str:
    return format_local(epoch_sec, "%Y%m%d_%H%M%S")


def status() -> dict[str, Any]:
    with _lock:
        synced = _last_sync_monotonic is not None
        age_sec = (
            round(time.monotonic() - _last_sync_monotonic, 3)
            if _last_sync_monotonic is not None
            else None
        )
        current_epoch = time.time() + _epoch_offset_sec
        timezone_offset_min = _timezone_offset_min
        timezone_name = _timezone_name
        client_epoch_sec = _last_client_epoch_sec
        client_iso = _last_client_iso

    return {
        "synced": synced,
        "age_sec": age_sec,
        "system_epoch_sec": time.time(),
        "calibrated_epoch_sec": current_epoch,
        "calibrated_local": format_local(current_epoch),
        "offset_sec": round(_epoch_offset_sec, 3),
        "timezone_offset_min": timezone_offset_min,
        "timezone": timezone_name,
        "last_client_epoch_sec": client_epoch_sec,
        "last_client_iso": client_iso,
    }
