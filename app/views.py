import json
from datetime import datetime
from pathlib import Path
import shutil
import logging
import threading
import time

from app import app
import cv2
from flask import request, jsonify, render_template, send_file, url_for, Response

from app.camera_modes import (
    camera_mode_key,
    get_supported_resolution_options,
    normalize_camera_mode,
    parse_camera_mode_key,
    sample_stream_fps,
)
from app.config_schema import validate_model_name, resolve_model_dir
from app.runtime_paths import (
    AI_CONFIG_PATH,
    CAMERA_CONFIG_PATH,
    MODEL_FILE_PATH,
    VIDEO_BASE_PATH,
)
from app.runtime import (
    build_runtime_status,
    cam_manager,
    get_detection_overlay,
    get_target_streams,
    reload_enabled_streams,
    start_runtime,
    stop_runtime,
    sync_infer_enable_from_config,
)
from app.services.config_service import ai_config_service
from app.services.camera_config_service import (
    camera_config_service,
    normalize_power_line_frequency,
    normalize_white_balance,
)
from inference.python_tensorrt.alarm_output import AlarmOutputController
from inference.python_tensorrt.ysl301 import (
    CHANNELS as YSL301_CHANNELS,
    DEFAULT_IDLE_PATTERN as YSL301_IDLE_PATTERN,
    LIGHT_STATES as YSL301_LIGHT_STATES,
    normalize_state_name as normalize_ysl301_state,
)

from app.utils import (
    to_bool,
    normalize_roi,
    )

# =========================================================
# 配置路径
# =========================================================

logger = logging.getLogger(__name__)
logger.info("AI config path: %s", AI_CONFIG_PATH)
logger.info("Camera config path: %s", CAMERA_CONFIG_PATH)
logger.info("Model directory: %s", MODEL_FILE_PATH)
logger.info("Video base directory: %s", VIDEO_BASE_PATH)

_mjpeg_active_clients = {}
_mjpeg_client_lock = threading.Lock()
_manual_output_lock = threading.Lock()
_manual_output_controller = None
_manual_output_signature = None


def read_ai_config():
    return ai_config_service.read()


def update_ai_config(mutator):
    return ai_config_service.update(mutator)


def _current_camera_settings_payload():
    status = cam_manager.get_status()
    defaults = {
        "width": status.get("width", 1920),
        "height": status.get("height", 1080),
        "fps": status.get("fps", 60),
        "exposure": status.get("exposure", 0),
        "gain": status.get("gain", 0),
        "white_balance": status.get("white_balance", "continuous"),
        "power_line_frequency": status.get("power_line_frequency", 1),
    }
    persisted = camera_config_service.read(defaults=defaults)

    width = int(status.get("width") or persisted["width"])
    height = int(status.get("height") or persisted["height"])
    fps = int(status.get("fps") or persisted["fps"])
    mode = normalize_camera_mode(width, height, fps)
    resolution = camera_mode_key(mode["width"], mode["height"])
    white_balance = normalize_white_balance(
        status.get("white_balance") or persisted["white_balance"]
    )
    power_line_frequency = normalize_power_line_frequency(
        status.get("power_line_frequency", persisted["power_line_frequency"])
    )

    return {
        "resolution": resolution,
        "width": mode["width"],
        "height": mode["height"],
        "fps": mode["fps"],
        "exposure": int(status.get("exposure", persisted["exposure"]) or 0),
        "gain": int(status.get("gain", persisted["gain"]) or 0),
        "white_balance": white_balance,
        "whiteBalance": white_balance,
        "power_line_frequency": power_line_frequency,
        "powerLineFrequency": power_line_frequency,
        "target": persisted.get("target", "high"),
        "supported_resolutions": get_supported_resolution_options(),
    }


def _apply_stream_mode(target, width, height, camera_fps):
    stream_mode = sample_stream_fps(width, height, camera_fps)
    updated_streams = []
    for stream in get_target_streams(target):
        stream.set_fps(stream_mode["fps"])
        stream.set_resolution(stream_mode["width"], stream_mode["height"])
        updated_streams.append(stream.name)
    return {
        **stream_mode,
        "updated_streams": updated_streams,
    }


def _resolution_key_from_status():
    status = cam_manager.get_status()
    return camera_mode_key(status.get("width") or 1920, status.get("height") or 1080)


def _normalize_resolution_key(value=None):
    if str(value or "").lower() in {"all", "high", "low"}:
        value = None
    if value:
        width, height = parse_camera_mode_key(value)
        normalize_camera_mode(width, height, 30)
        return camera_mode_key(width, height)
    return _resolution_key_from_status()


def _ensure_roi_profiles(model_cfg, active_key=None):
    profiles = model_cfg.get("rois_by_resolution")
    if not isinstance(profiles, dict):
        profiles = {}
        model_cfg["rois_by_resolution"] = profiles

    existing_active_key = str(
        model_cfg.get("active_roi_resolution") or _resolution_key_from_status()
    )
    current_rois = model_cfg.get("rois", [])
    if (
        existing_active_key not in profiles
        and isinstance(current_rois, list)
        and current_rois
    ):
        profiles[existing_active_key] = current_rois

    active_key = active_key or existing_active_key
    model_cfg["active_roi_resolution"] = active_key

    return profiles, active_key


def _activate_roi_profile(model_cfg, resolution_key):
    profiles, _ = _ensure_roi_profiles(model_cfg, resolution_key)
    model_cfg["active_roi_resolution"] = resolution_key
    model_cfg["rois"] = list(profiles.get(resolution_key, []))
    return len(model_cfg["rois"])


def _roi_display_state_from_zone(roi, zone):
    if not zone:
        return "safe", "#22c55e"

    try:
        person_count = int(zone.get("person_count", 0) or 0)
    except Exception:
        person_count = 0
    try:
        warning_count = int(zone.get("warning_count", 0) or 0)
    except Exception:
        warning_count = 0
    if person_count <= 0 and warning_count <= 0:
        return "safe", "#22c55e"

    roi_type = str(zone.get("roi_type") or roi.get("roi_type") or "")
    if person_count <= 0 or roi_type == "warning_zone":
        return "warning", "#f59e0b"
    return "alarm", "#ef4444"


def _attach_roi_display_state(rois, overlay):
    zones = {
        str(zone.get("roi_id", "")): zone
        for zone in (overlay or {}).get("zone_summary", []) or []
        if isinstance(zone, dict)
    }
    enriched = []
    for roi in rois or []:
        if not isinstance(roi, dict):
            continue
        item = dict(roi)
        zone = zones.get(str(item.get("roi_id", "")))
        display_status, display_color = _roi_display_state_from_zone(item, zone)
        item["display_status"] = display_status
        item["display_color"] = display_color
        item["person_count"] = int((zone or {}).get("person_count", 0) or 0)
        item["warning_count"] = int((zone or {}).get("warning_count", 0) or 0)
        enriched.append(item)
    return enriched

# =========================================================
# 基础接口
# =========================================================

@app.route("/")
def index():
    return jsonify({
        "status": "success",
        "message": "API is running"
    })


@app.route("/api/runtime/status", methods=["GET"])
@app.route("/api/system/status", methods=["GET"])
def get_runtime_status():
    return jsonify({
        "status": "success",
        "data": build_runtime_status(),
    })


@app.route("/api/stream/config", methods=["GET"])
def get_stream_config():
    try:
        return jsonify({
            "status": "success",
            "data": _current_camera_settings_payload(),
        })
    except Exception as e:
        logger.exception("Failed to read camera stream config")
        return jsonify({
            "status": "error",
            "message": str(e),
        }), 500

# =========================================================
# 推流接口
# =========================================================

@app.route("/api/stream/mjpeg", methods=["GET"])
def stream_mjpeg_preview():
    """Low-latency preview stream that always serves the newest frame."""
    target = request.args.get("target", "high")
    try:
        preview_fps = max(1, min(60, int(request.args.get("fps", "30"))))
    except (TypeError, ValueError):
        preview_fps = 30
    try:
        jpeg_quality = max(35, min(95, int(request.args.get("quality", "65"))))
    except (TypeError, ValueError):
        jpeg_quality = 65
    try:
        max_width = max(0, int(request.args.get("max_width", "1280")))
    except (TypeError, ValueError):
        max_width = 1280
    include_overlay = to_bool(request.args.get("overlay", "0"))

    streams = get_target_streams(target)
    stream = streams[0] if streams else None

    if stream is None:
        return jsonify({
            "status": "error",
            "message": "No stream is available for MJPEG preview",
        }), 404

    client_key = getattr(stream, "name", target)
    client_id = request.args.get("t") or f"{time.time()}-{id(request)}"
    with _mjpeg_client_lock:
        _mjpeg_active_clients[client_key] = client_id

    frame_interval = 1.0 / preview_fps

    def generate():
        last_frame_time = 0.0
        next_frame_at = 0.0

        try:
            while True:
                with _mjpeg_client_lock:
                    if _mjpeg_active_clients.get(client_key) != client_id:
                        break

                frame, frame_time = stream.inference.get_frame_snapshot(
                    include_overlay=include_overlay,
                )
                if frame is None:
                    time.sleep(0.02)
                    continue

                if frame_time and frame_time <= last_frame_time:
                    time.sleep(0.002)
                    continue

                now = time.perf_counter()
                if now < next_frame_at:
                    time.sleep(next_frame_at - now)
                next_frame_at = time.perf_counter() + frame_interval

                if max_width and frame.shape[1] > max_width:
                    scale = max_width / frame.shape[1]
                    frame = cv2.resize(
                        frame,
                        (max_width, max(2, int(round(frame.shape[0] * scale / 2) * 2))),
                        interpolation=cv2.INTER_AREA,
                    )

                ok, encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality],
                )
                if not ok:
                    time.sleep(0.01)
                    continue

                frame_bytes = encoded.tobytes()
                last_frame_time = frame_time or time.time()
                frame_age_ms = max(0.0, (time.time() - last_frame_time) * 1000.0)
                if hasattr(stream, "mark_mjpeg_frame"):
                    stream.mark_mjpeg_frame()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Cache-Control: no-store\r\n"
                    b"X-Frame-Time: " + f"{last_frame_time:.6f}".encode("ascii") + b"\r\n"
                    b"X-Frame-Age-Ms: " + f"{frame_age_ms:.1f}".encode("ascii") + b"\r\n"
                    b"Content-Length: " + str(len(frame_bytes)).encode("ascii") + b"\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
        finally:
            with _mjpeg_client_lock:
                if _mjpeg_active_clients.get(client_key) == client_id:
                    _mjpeg_active_clients.pop(client_key, None)

    response = Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.route("/api/stream/start", methods=["POST", "GET"])
def start_streams():
    try:
        start_runtime()
        return jsonify({
            "status": "success",
            "message": "双路推流已启动"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"启动推流失败: {e}"
        }), 500


@app.route("/api/stream/stop", methods=["POST", "GET"])
def stop_streams():
    try:
        stop_runtime()
        return jsonify({
            "status": "success",
            "message": "双路推流已停止"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"停止推流失败: {e}"
        }), 500


@app.route("/api/stream/exposure", methods=["POST"])
def set_exposure():
    data = request.get_json(silent=True) or {}

    if "value" not in data:
        return jsonify({
            "status": "error",
            "message": "缺少 value 参数"
        }), 400

    try:
        value = int(data["value"])
        target = data.get("target", "high")
        cam_manager.set_exposure(value)
        settings = camera_config_service.update({
            "exposure": value,
            "target": target,
        })

        return jsonify({
            "status": "success",
            "message": f"曝光已设置为: {value}",
            "data": {
                "exposure": settings["exposure"],
                "target": settings["target"],
            },
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"设置曝光失败: {e}"
        }), 400


@app.route("/api/stream/gain", methods=["POST"])
def set_gain():
    data = request.get_json(silent=True) or {}

    if "value" not in data:
        return jsonify({
            "status": "error",
            "message": "缺少 gain 参数"
        }), 400

    try:
        value = int(float(data["value"]))
        if value < 0:
            raise ValueError("gain must be >= 0")

        target = data.get("target", "high")
        cam_manager.set_gain(value)
        settings = camera_config_service.update({
            "gain": value,
            "target": target,
        })

        return jsonify({
            "status": "success",
            "message": f"增益已设置为: {settings['gain']}",
            "data": {
                "gain": settings["gain"],
                "target": settings["target"],
            },
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"设置增益失败: {e}"
        }), 400


@app.route("/api/stream/white_balance", methods=["POST"])
def set_white_balance():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")

    if mode is None and "auto" in data:
        mode = "continuous" if to_bool(data.get("auto")) else "off"

    try:
        mode = normalize_white_balance(mode)
        target = data.get("target", "high")
        cam_manager.set_white_balance(mode)
        settings = camera_config_service.update({
            "white_balance": mode,
            "target": target,
        })

        return jsonify({
            "status": "success",
            "message": f"白平衡已设置为: {settings['white_balance']}",
            "data": {
                "mode": settings["white_balance"],
                "target": settings["target"],
            },
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"设置白平衡失败: {e}"
        }), 400


@app.route("/api/stream/power_line_frequency", methods=["POST"])
def set_power_line_frequency():
    data = request.get_json(silent=True) or {}

    raw_value = data.get("value", data.get("mode", data.get("frequency")))

    try:
        value = normalize_power_line_frequency(raw_value)
        target = data.get("target", "high")
        cam_manager.set_power_line_frequency(value)
        settings = camera_config_service.update({
            "power_line_frequency": value,
            "target": target,
        })

        return jsonify({
            "status": "success",
            "message": f"抗频闪已设置为: {settings['power_line_frequency']}",
            "data": {
                "power_line_frequency": settings["power_line_frequency"],
                "target": settings["target"],
            },
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"设置抗频闪失败: {e}"
        }), 400


@app.route("/api/stream/resolution", methods=["POST"])
def set_resolution():
    data = request.get_json(silent=True) or {}

    if "width" not in data or "height" not in data:
        return jsonify({
            "status": "error",
            "message": "缺少 width 或 height 参数"
        }), 400

    try:
        width = int(data["width"])
        height = int(data["height"])
        target = data.get("target", "high")
        current_fps = int(cam_manager.get_status().get("fps") or 30)
        mode = normalize_camera_mode(width, height, current_fps)

        # 让硬件管理器修改参数并重启硬件取流
        cam_manager.set_fps(mode["fps"])
        cam_manager.set_resolution(mode["width"], mode["height"])

        stream_mode = _apply_stream_mode(
            target,
            mode["width"],
            mode["height"],
            mode["fps"],
        )

        resolution_key = camera_mode_key(mode["width"], mode["height"])

        def activate_profile(cfg):
            model_cfg = cfg.setdefault("model", {})
            return _activate_roi_profile(model_cfg, resolution_key)

        cfg, active_roi_count = update_ai_config(activate_profile)
        reloaded = reload_enabled_streams()
        settings = camera_config_service.update({
            "resolution": resolution_key,
            "width": mode["width"],
            "height": mode["height"],
            "fps": mode["fps"],
            "target": target,
        })

        return jsonify({
            "status": "success",
            "message": (
                f"分辨率已设置为 {mode['width']}x{mode['height']}, "
                f"fps={mode['fps']}, target={target}"
            ),
            "data": {
                **mode,
                "resolution_key": resolution_key,
                "camera_fps": mode["fps"],
                "stream_fps": stream_mode["fps"],
                "stream_width": stream_mode["width"],
                "stream_height": stream_mode["height"],
                "stream_sampled": stream_mode["sampled"],
                "stream_sample_reason": stream_mode["sample_reason"],
                "updated_streams": stream_mode["updated_streams"],
                "active_roi_count": active_roi_count,
                "reloaded_streams": reloaded,
                "saved_resolution": settings["resolution"],
            },
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"设置分辨率失败: {e}"
        }), 400


@app.route("/api/stream/fps", methods=["POST"])
def set_fps():
    data = request.get_json(silent=True) or {}

    if "value" not in data:
        return jsonify({
            "status": "error",
            "message": "缺少 fps 参数"
        }), 400

    try:
        fps = int(data["value"])
        target = data.get("target", "high")
        cam_status = cam_manager.get_status()
        mode = normalize_camera_mode(
            cam_status.get("width") or 1920,
            cam_status.get("height") or 1080,
            fps,
        )

        # 让硬件管理器修改参数并重启硬件取流
        cam_manager.set_fps(mode["fps"])

        stream_mode = sample_stream_fps(
            mode["width"],
            mode["height"],
            mode["fps"],
        )
        for stream in get_target_streams(target):
            stream.set_fps(stream_mode["fps"])
        settings = camera_config_service.update({
            "width": mode["width"],
            "height": mode["height"],
            "fps": mode["fps"],
            "target": target,
        })

        return jsonify({
            "status": "success",
            "message": f"FPS 已设置为 {mode['fps']}, target={target}",
            "data": {
                **mode,
                "camera_fps": mode["fps"],
                "stream_fps": stream_mode["fps"],
                "stream_width": stream_mode["width"],
                "stream_height": stream_mode["height"],
                "stream_sampled": stream_mode["sampled"],
                "stream_sample_reason": stream_mode["sample_reason"],
                "target": settings["target"],
            },
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"设置 FPS 失败: {e}"
        }), 400


# =========================================================
# AI检测配置接口
# =========================================================

@app.route("/api/detection/detect", methods=["POST"])
def update_inference_configuration():
    """
    更新检测配置，并根据 detectionEnabled 开启/关闭推理。

    前端请求示例：
    {
        "detectionEnabled": true,
        "detectionModel": "yolo11",
        "detectionThreshold": 0.35,
        "overlapRate": 0.45,
        "target": "high"
    }
    """
    data = request.get_json(silent=True) or {}

    try:
        def mutate(cfg):
            model_cfg = cfg.setdefault("model", {})

            target = str(data.get(
                "target",
                model_cfg.get("infer_target", "high")
            )).lower()

            if target not in ["high", "low", "all"]:
                raise ValueError("target 必须是 high、low 或 all")

            model_cfg["infer_target"] = target

            if "detectionEnabled" in data:
                detect_enable = to_bool(data["detectionEnabled"])
                model_cfg["detect_enable"] = detect_enable
            else:
                detect_enable = to_bool(model_cfg.get("detect_enable", False))

            if "detectionModel" in data:
                model_cfg["model_name"] = validate_model_name(data["detectionModel"])

            if "detectionThreshold" in data:
                model_cfg["conf_thres"] = float(data["detectionThreshold"])

            if "overlapRate" in data:
                overlap_thres = float(data["overlapRate"])
                for roi in model_cfg.get("rois", []):
                    roi["overlap_thres"] = overlap_thres
                profiles = model_cfg.get("rois_by_resolution", {})
                if isinstance(profiles, dict):
                    for rois in profiles.values():
                        if isinstance(rois, list):
                            for roi in rois:
                                if isinstance(roi, dict):
                                    roi["overlap_thres"] = overlap_thres

            return {"detect_enable": detect_enable, "target": target}

        cfg, result = update_ai_config(mutate)

        changed_streams = sync_infer_enable_from_config(cfg)

        # changed_streams = set_infer_enable(
        #     enable=detect_enable,
        #     target=target
        # )

        return jsonify({
            "status": "success",
            "message": "检测设置已更新",
            "data": {
                "detect_enable": result["detect_enable"],
                "target": result["target"],
                "changed_streams": changed_streams
            }
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400


@app.route("/api/detection/fetch_regions", methods=["GET"])
def get_detection_regions():
    """
    获取检测区域。
    """
    try:
        cfg = read_ai_config()
        model_cfg = cfg.get("model", {})
        profiles, active_key = _ensure_roi_profiles(model_cfg)
        requested_key = _normalize_resolution_key(
            request.args.get("resolution_key") or active_key
        )
        rois = profiles.get(requested_key, model_cfg.get("rois", []))

        return jsonify({
            "status": "success",
            "rois": rois,
            "active_resolution": active_key,
            "selected_resolution": requested_key,
            "rois_by_resolution": profiles,
            "supported_resolutions": get_supported_resolution_options(),
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"获取检测区域失败: {e}",
            "rois": [],
            "rois_by_resolution": {},
        }), 400


@app.route("/api/detection/overlay", methods=["GET"])
def get_detection_overlay_state():
    """
    获取实时预览叠层数据。视频仍走低延迟直通流，前端用这些坐标画 ROI/AI 框。
    """
    try:
        target = request.args.get("target", "high")
        max_age_sec = float(request.args.get("max_age_sec", 1.0))
        cfg = read_ai_config()
        model_cfg = cfg.get("model", {})
        active_resolution = model_cfg.get("active_roi_resolution") or _resolution_key_from_status()
        rois = model_cfg.get("rois", [])
        overlay = get_detection_overlay(target=target, max_age_sec=max_age_sec)
        rois = _attach_roi_display_state(rois, overlay)

        return jsonify({
            "status": "success",
            "data": {
                "target": target,
                "active_resolution": active_resolution,
                "rois": rois,
                "overlay": overlay,
            },
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"获取检测叠层失败: {e}",
            "data": {
                "target": request.args.get("target", "high"),
                "rois": [],
                "overlay": {
                    "detections": [],
                    "zone_summary": [],
                    "stale": True,
                },
            },
        }), 400


@app.route("/api/detection/save_regions", methods=["POST"])
def update_detection_regions():
    """
    保存检测区域。

    前端请求示例：
    {
        "rois": [...]
    }
    """
    data = request.get_json(silent=True) or {}

    if "rois" not in data:
        return jsonify({
            "status": "error",
            "message": "缺少 rois 参数"
        }), 400

    try:
        raw_rois = data["rois"]
        resolution_key = _normalize_resolution_key(
            data.get("resolution_key") or data.get("target")
        )

        if not isinstance(raw_rois, list):
            raise ValueError("rois 必须是数组")

        def mutate(cfg):
            model_cfg = cfg.setdefault("model", {})
            profiles, active_key = _ensure_roi_profiles(model_cfg, resolution_key)
            normalized_rois = [
                {
                    **normalize_roi(roi, index),
                    "target": "all",
                    "resolution_key": resolution_key,
                }
                for index, roi in enumerate(raw_rois)
            ]
            profiles[resolution_key] = normalized_rois
            model_cfg["rois_by_resolution"] = profiles
            if active_key == resolution_key:
                model_cfg["rois"] = normalized_rois
                model_cfg["active_roi_resolution"] = resolution_key
            return len(normalized_rois)

        cfg, roi_count = update_ai_config(mutate)

        reloaded = sync_infer_enable_from_config(cfg)

        return jsonify({
            "status": "success",
            "message": "检测区域已保存",
            "data": {
                "roi_count": roi_count,
                "resolution_key": resolution_key,
                "reloaded": reloaded,
            }
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400
        
        
# =========================================================
# 模型管理接口
# =========================================================
@app.route("/api/models/upload", methods=["POST"])
def upload_model():
    """
    接收模型文件上传。
    接收字段:
    - model_name: 字符串
    - engine_file: .engine 文件
    - txt_file: .txt 文件
    """
    model_name = request.form.get("model_name")
    engine_file = request.files.get("engine_file")
    txt_file = request.files.get("txt_file")

    # 检查文件是否齐全
    if not model_name or not engine_file or not txt_file:
        return jsonify({
            "status": "error",
            "message": "缺少必要参数：需要 model_name, engine_file, txt_file"
        }), 400

    try:
        model_name = validate_model_name(model_name)
    except ValueError as error:
        return jsonify({"status": "error", "message": str(error)}), 400

    # 检查是否有以 .engine 后缀的文件
    if not str(engine_file.filename or "").lower().endswith(".engine"):
        return jsonify({"status": "error", "message": "engine_file 必须是 .engine 文件"}), 400

    # 检查是否有以 .txt 后缀的文件
    if not str(txt_file.filename or "").lower().endswith(".txt"):
        return jsonify({"status": "error", "message": "txt_file 必须是 .txt 文件"}), 400

    try:
        model_name, save_dir = resolve_model_dir(MODEL_FILE_PATH, model_name)
        engine_path = save_dir / f"{model_name}.engine"
        txt_path = save_dir / f"{model_name}.txt"

        def mutate(cfg):
            model_names = cfg.get("model_names") or []
            if not isinstance(model_names, list):
                model_names = []

            if model_name in model_names:
                raise ValueError(f"模型 '{model_name}' 已存在，请使用其他名称")

            save_dir.mkdir(parents=True, exist_ok=True)
            engine_file.save(str(engine_path))
            txt_file.save(str(txt_path))

            model_names.append(model_name)
            cfg["model_names"] = model_names

        update_ai_config(mutate)

        return jsonify({
            "status": "success",
            "message": f"模型 '{model_name}' 成功上传并配置",
            "data": {
                "model_name": model_name,
                "engine_path": str(engine_path),
                "txt_path": str(txt_path)
            }
        })

    except ValueError as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"上传模型失败: {str(e)}"
        }), 500


@app.route("/api/models/list", methods=["GET"])
def get_model_list():
    """
    获取当前已配置的模型名称列表
    """
    try:
        cfg = read_ai_config()
        # 容错处理：确保返回的一定是 list
        model_names = cfg.get("model_names") or [] 
        if not isinstance(model_names, list):
            model_names = [] # 没有字段 model_names 则为空列表

        return jsonify({
            "status": "success",
            "models": model_names # 直接返回字段列表(没有时返回空列表)
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"获取模型列表失败: {str(e)}"
        }), 500


@app.route("/api/models/delete", methods=["POST"])
def delete_model():
    """
    删除指定的模型及其文件
    """
    data = request.get_json(silent=True) or {}
    model_name = data.get("model_name")

    if not model_name:
        return jsonify({"status": "error", "message": "缺少 model_name 参数"}), 400

    try:
        model_name = validate_model_name(model_name)
    except ValueError as error:
        return jsonify({"status": "error", "message": str(error)}), 400
        
    try:
        def mutate(cfg):
            model_names = cfg.get("model_names") or []
            if not isinstance(model_names, list):
                model_names = []

            if model_name not in model_names:
                raise FileNotFoundError(f"模型 '{model_name}' 不存在")

            model_names.remove(model_name)
            cfg["model_names"] = model_names

        update_ai_config(mutate)

        model_name, model_dir = resolve_model_dir(MODEL_FILE_PATH, model_name)
        if model_dir.exists() and model_dir.is_dir():
            shutil.rmtree(str(model_dir))
            
        return jsonify({
            "status": "success",
            "message": f"模型 '{model_name}' 及相关文件删除成功"
        })

    except FileNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"删除模型失败: {str(e)}"
        }), 500


# =========================
# 异常检测GPIO配置接口
# =========================

def normalize_gpio_output_level(value):
    """
    归一化 GPIO 输出电平。
    支持前端传：
    - 1 / 0
    - true / false
    - "high" / "low"
    - "on" / "off"
    - "高" / "低"
    """
    if isinstance(value, bool):
        return 1 if value else 0

    if isinstance(value, (int, float)):
        if float(value) == 1:
            return 1
        if float(value) == 0:
            return 0
        raise ValueError("output_level 只能是 0 或 1")

    value_str = str(value).strip().lower()

    if value_str in ["1", "true", "high", "on", "高", "高电平"]:
        return 1

    if value_str in ["0", "false", "low", "off", "低", "低电平"]:
        return 0

    raise ValueError("output_level 只能是 0/1、true/false、high/low")


def normalize_gpio_pins(value):
    """
    归一化 GPIO 引脚列表。
    支持前端传：
    - 单个数字：18
    - 数组： [7, 11, 18]
    """
    pins = value if isinstance(value, list) else [value]

    out = []
    for p in pins:
        try:
            pn = int(p)
        except Exception:
            continue
        if pn > 0:
            out.append(pn)

    out = sorted(list(dict.fromkeys(out)))
    if not out:
        raise ValueError("gpio 必须是大于 0 的整数或整数数组")
    return out


def normalize_serial_alarm_pattern(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("serial alarm pattern must be an object")

    channels = {"red", "yellow", "green", "buzzer"}
    out = {}
    for channel, state in value.items():
        channel_key = str(channel).strip().lower()
        if channel_key not in channels:
            raise ValueError(f"unsupported serial alarm channel: {channel}")
        out[channel_key] = str(state).strip().lower().replace("-", "_")
    return out


def normalize_serial_output(value):
    if not isinstance(value, dict):
        raise ValueError("serial must be an object")

    out = {}
    if "enabled" in value:
        out["enabled"] = to_bool(value["enabled"])
    if "type" in value:
        out["type"] = str(value["type"]).strip().lower()
    if "port" in value:
        out["port"] = str(value["port"]).strip() or "auto"

    for field in ("baudrate", "address"):
        if field in value:
            out[field] = int(value[field])

    for field in ("timeout", "write_timeout", "writeTimeout", "command_delay", "commandDelay"):
        if field in value:
            out[field] = float(value[field])

    for field in ("alarm", "warning", "safe", "idle"):
        pattern = normalize_serial_alarm_pattern(value.get(field))
        if pattern is not None:
            out[field] = pattern

    return out


def normalize_manual_output_channels(data):
    out = dict(YSL301_IDLE_PATTERN)
    raw_channels = data.get("channels")

    if raw_channels is not None:
        if not isinstance(raw_channels, dict):
            raise ValueError("channels must be an object")

        for channel, state in raw_channels.items():
            channel_key = str(channel).strip().lower()
            if channel_key not in YSL301_CHANNELS:
                raise ValueError(f"unsupported manual output channel: {channel}")

            state_key = normalize_ysl301_state(state)
            if state_key not in YSL301_LIGHT_STATES:
                raise ValueError(f"unsupported manual output state: {state}")

            out[channel_key] = state_key
        return out

    channel = str(data.get("channel", "") or "").strip().lower()
    active = to_bool(data.get("active", False))
    if not channel:
        if active:
            raise ValueError("channel or channels is required")
        return out

    if channel not in YSL301_CHANNELS:
        raise ValueError(f"unsupported manual output channel: {channel}")

    default_active_state = "on"
    raw_state = data.get("state", default_active_state if active else "off")
    state_key = normalize_ysl301_state(raw_state)
    if not active:
        state_key = "off"
    if state_key not in YSL301_LIGHT_STATES:
        raise ValueError(f"unsupported manual output state: {raw_state}")

    out[channel] = state_key
    return out


def get_manual_output_controller():
    global _manual_output_controller, _manual_output_signature

    cfg = dict(read_ai_config().get("exception_output", {}) or {})
    signature = json.dumps(cfg, sort_keys=True, default=str)

    with _manual_output_lock:
        if (
            _manual_output_controller is None
            or _manual_output_signature != signature
        ):
            if _manual_output_controller is not None:
                _manual_output_controller.close()

            _manual_output_controller = AlarmOutputController(cfg)
            _manual_output_signature = signature

        return _manual_output_controller


def apply_manual_output_channels(channels, target="all"):
    active = any(
        normalize_ysl301_state(state) != "off"
        for state in channels.values()
    )

    for stream in get_target_streams(target):
        setter = getattr(stream.inference, "set_alarm_output_channels", None)
        if callable(setter) and setter(channels):
            return [stream.name]

    controller = get_manual_output_controller()
    if controller.set_manual_channels(channels):
        return ["manual"]

    if not active:
        return ["noop"]

    raise RuntimeError("serial alarm output is not enabled or unavailable")


@app.route("/api/detection/exception_output", methods=["POST"])
def update_exception_output_configuration():
    """
    异常输出配置。

    前端请求示例：
    {
        "gpio": [7, 11, 18],
        "output_level": 1,
        "duration": 5
    }

    参数说明：
    - gpio: Jetson GPIO 引脚号
    - output_level: 输出电平，1=高电平，0=低电平
    - duration: 持续时间，单位秒；0 表示一直保持
    """
    data = request.get_json(silent=True) or {}

    gpio_raw = data.get("gpio", data.get("gpio_pin", data.get("gpioPin")))
    level_raw = data.get(
        "output_level",
        data.get("level", data.get("outputLevel"))
    )
    duration_raw = data.get(
        "duration",
        data.get("duration_sec", data.get("durationSec", 0))
    )
    serial_raw = data.get("serial", data.get("ysl301"))

    if gpio_raw is None and serial_raw is None:
        return jsonify({
            "status": "error",
            "message": "缺少 gpio 或 serial 参数"
        }), 400

    if gpio_raw is not None and level_raw is None:
        return jsonify({
            "status": "error",
            "message": "缺少 output_level 参数"
        }), 400

    try:
        exception_output = dict(read_ai_config().get("exception_output", {}) or {})
        if gpio_raw is not None:
            exception_output["gpio"] = normalize_gpio_pins(gpio_raw)
            exception_output["output_level"] = normalize_gpio_output_level(level_raw)
        else:
            exception_output.setdefault("gpio", [])
            exception_output.setdefault("output_level", 1)

        duration = float(duration_raw)
        if duration < 0:
            raise ValueError("duration 必须大于等于 0，0 表示一直保持")

        # 如果是整数秒，写入 YAML 时保持为 int，避免 5.0
        if duration.is_integer():
            duration = int(duration)

        exception_output["duration"] = duration
        if serial_raw is not None:
            exception_output["serial"] = normalize_serial_output(serial_raw)

        def mutate(cfg):
            cfg["exception_output"] = exception_output

        update_ai_config(mutate)

        # 如果推理流运行中，让它重新读取配置
        reloaded = reload_enabled_streams()

        return jsonify({
            "status": "success",
            "message": "异常输出配置已更新",
            "data": {
                "exception_output": exception_output,
                "reloaded": reloaded
            }
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400


@app.route("/api/detection/exception_output/test", methods=["POST"])
def test_exception_output_configuration():
    data = request.get_json(silent=True) or {}
    active = to_bool(data.get("active", True))
    duration = float(data.get("duration", data.get("duration_sec", data.get("durationSec", 2))) or 0)
    if duration < 0:
        return jsonify({
            "status": "error",
            "message": "duration must be greater than or equal to 0",
        }), 400

    try:
        target = data.get("target", "high")
        triggered = []
        for stream in get_target_streams(target):
            stream.inference.trigger_alarm_output(active=active, duration=duration)
            triggered.append(stream.name)

        return jsonify({
            "status": "success",
            "data": {
                "active": active,
                "duration": duration,
                "target": target,
                "triggered": triggered,
            },
        })
    except Exception as e:
        logger.exception("Failed to test exception output")
        return jsonify({
            "status": "error",
            "message": str(e),
        }), 400


@app.route("/api/detection/exception_output/manual", methods=["POST"])
def manual_exception_output_control():
    data = request.get_json(silent=True) or {}

    try:
        channels = normalize_manual_output_channels(data)
        target = data.get("target", "all")
        applied_by = apply_manual_output_channels(channels, target=target)
        active_channels = [
            channel for channel, state in channels.items()
            if normalize_ysl301_state(state) != "off"
        ]

        return jsonify({
            "status": "success",
            "data": {
                "channels": channels,
                "active_channels": active_channels,
                "target": target,
                "applied_by": applied_by,
            },
        })
    except Exception as e:
        logger.exception("Failed to set manual exception output")
        return jsonify({
            "status": "error",
            "message": str(e),
        }), 400


# =========================
# Flask 默认辅助函数
# =========================

def form_errors(form):
    error_messages = []

    for field, errors in form.errors.items():
        for error in errors:
            message = "Error in the %s field - %s" % (
                getattr(form, field).label.text,
                error
            )
            error_messages.append(message)

    return error_messages


@app.route("/<file_name>.txt")
def send_text_file(file_name):
    """
    Send static txt file.
    """
    file_dot_text = file_name + ".txt"
    return app.send_static_file(file_dot_text)


@app.after_request
def add_header(response):
    """
    Disable browser cache.
    """
    response.headers["X-UA-Compatible"] = "IE=Edge,chrome=1"
    response.headers["Cache-Control"] = "public, max-age=0"
    return response


@app.errorhandler(404)
def page_not_found(error):
    """
    Custom 404 page.
    """
    if request.path.startswith("/api/"):
        return jsonify({
            "status": "error",
            "message": "API endpoint not found",
            "path": request.path,
        }), 404

    return render_template("404.html"), 404


# =========================================================
# 本地视频录制配置接口
# =========================================================

@app.route("/api/record/config", methods=["POST", "GET"])
def handle_record_config():
    """
    前端配置视频保存时间接口。
    注意：每次修改时间后在下个视频开始才能生效 
    因为CamStream每次只在开始录制新视频前读取AIConfig.yaml中的录制时间
    
    POST 请求示例：
    {
        "duration_min": 10
    }
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        
        if "duration_min" not in data:
            return jsonify({
                "status": "error",
                "message": "缺少必要参数：duration_min"
            }), 400
            
        try:
            duration_min = float(data["duration_min"])
            if duration_min <= 0:
                raise ValueError("单个录制分段时长必须大于 0")
                
            def mutate(cfg):
                record_cfg = cfg.setdefault("record", {})
                record_cfg["duration_min"] = duration_min

            update_ai_config(mutate)
            
            return jsonify({
                "status": "success",
                "message": f"单个视频保存时限成功更新为: {duration_min} 分钟",
                "data": {
                    "duration_min": duration_min
                }
            })
            
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"更新录制配置失败: {str(e)}"
            }), 400
            
    else:
        # GET 请求：返回当前配置的时长
        try:
            cfg = read_ai_config()
            duration_min = cfg.get("record", {}).get("duration_min", 10)
            return jsonify({
                "status": "success",
                "duration_min": duration_min
            })
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"读取录制配置失败: {str(e)}"
            }), 500


# =========================================================
# 视频回放与下载接口
# =========================================================

VALID_RECORD_TARGETS = {"cam_high", "cam_low"}


def _get_record_target_dir(target):
    target = str(target or "cam_high")
    if target not in VALID_RECORD_TARGETS:
        raise ValueError("target 必须是 cam_high 或 cam_low")
    return target, VIDEO_BASE_PATH / "video" / target


def _parse_record_timestamp(filename):
    stem = Path(filename).stem
    try:
        return datetime.strptime(stem, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def _build_record_item(file_path, target):
    stat = file_path.stat()
    start_at = _parse_record_timestamp(file_path.name)
    metadata_path = file_path.with_suffix(".json")
    metadata = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}

    return {
        "filename": file_path.name,
        "title": file_path.stem,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "created_at": stat.st_mtime,
        "target": target,
        "date_key": start_at.strftime("%Y-%m-%d") if start_at else "",
        "start_at": metadata.get("start_at") or (start_at.isoformat() if start_at else None),
        "duration_sec": metadata.get("duration_sec"),
        "has_target": metadata.get("has_target"),
        "download_url": url_for(
            "download_record",
            filename=file_path.name,
            target=target,
            download=1,
            _external=False,
        ),
        "play_url": url_for(
            "download_record",
            filename=file_path.name,
            target=target,
            download=0,
            _external=False,
        ),
    }


@app.route("/api/record/list", methods=["GET"])
def get_record_list():
    """
    根据日期获取视频列表
    GET 示例: /api/record/list?date=2026-05-22&target=cam_high
    """
    try:
        target, video_dir = _get_record_target_dir(request.args.get("target", "cam_high"))
    except ValueError as error:
        return jsonify({"status": "error", "message": str(error)}), 400

    date_str = (request.args.get("date") or "").strip()
    date_prefix = date_str.replace("-", "")
    if date_prefix and (len(date_prefix) != 8 or not date_prefix.isdigit()):
        return jsonify({"status": "error", "message": "date 必须是 YYYY-MM-DD 或 YYYYMMDD"}), 400

    if not video_dir.exists():
        return jsonify({"status": "success", "data": [], "target": target, "date_filter": date_str})

    search_pattern = f"{date_prefix}*.mkv" if date_prefix else "*.mkv"
    files_info = [
        _build_record_item(file_path, target)
        for file_path in video_dir.glob(search_pattern)
        if file_path.is_file()
    ]
    files_info.sort(key=lambda item: item["filename"], reverse=True)

    return jsonify({
        "status": "success",
        "data": files_info,
        "target": target,
        "date_filter": date_str,
    })


@app.route("/api/record/download", methods=["GET"])
def download_record():
    """
    获取具体的视频文件。
    GET 示例:
      下载: /api/record/download?filename=20260522_143000.mkv&target=cam_high
      播放: /api/record/download?filename=20260522_143000.mkv&target=cam_high&download=0
    """
    try:
        target, video_dir = _get_record_target_dir(request.args.get("target", "cam_high"))
    except ValueError as error:
        return jsonify({"status": "error", "message": str(error)}), 400

    filename = (request.args.get("filename") or "").strip()
    if not filename:
        return jsonify({"status": "error", "message": "缺少 filename 参数"}), 400

    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"status": "error", "message": "非法的文件名"}), 400

    file_path = video_dir / filename
    if not file_path.exists() or not file_path.is_file():
        return jsonify({"status": "error", "message": "视频文件不存在"}), 404

    try:
        download_flag = str(request.args.get("download", "1")).lower()
        as_attachment = download_flag not in {"0", "false", "no"}
        return send_file(
            str(file_path),
            as_attachment=as_attachment,
            download_name=filename,
            mimetype="video/x-matroska",
            conditional=True,
        )
    except Exception as error:
        return jsonify({"status": "error", "message": f"文件获取失败: {str(error)}"}), 500


@app.route("/api/record/delete", methods=["POST"])
def delete_record():
    """
    删除后端磁盘中的真实视频文件
    POST 示例:
    {
        "target": "cam_high",
        "filenames": ["20260522_143000.mkv"]
    }
    """
    data = request.get_json(silent=True) or {}

    try:
        target, video_dir = _get_record_target_dir(data.get("target", "cam_high"))
    except ValueError as error:
        return jsonify({"status": "error", "message": str(error)}), 400

    filenames = data.get("filenames")
    if not isinstance(filenames, list) or not filenames:
        return jsonify({"status": "error", "message": "filenames 必须是非空数组"}), 400

    deleted = []
    not_found = []

    for filename in filenames:
        filename = str(filename or "").strip()
        if not filename:
            continue
        if "/" in filename or "\\" in filename or ".." in filename:
            return jsonify({"status": "error", "message": f"非法的文件名: {filename}"}), 400

        file_path = video_dir / filename
        metadata_path = file_path.with_suffix(".json")

        if not file_path.exists() or not file_path.is_file():
            not_found.append(filename)
            continue

        try:
            file_path.unlink()
            if metadata_path.exists() and metadata_path.is_file():
                metadata_path.unlink()
            deleted.append(filename)
        except Exception as error:
            return jsonify({
                "status": "error",
                "message": f"删除文件失败: {filename}, {str(error)}",
            }), 500

    return jsonify({
        "status": "success",
        "target": target,
        "deleted": deleted,
        "not_found": not_found,
    })
