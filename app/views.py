from pathlib import Path

from app import app
from flask import request, jsonify, render_template

from app.Cam.CamStream import CamStream
from app.Cam.CamManager import CamManager

from app.utils import (
    read_yaml,
    write_yaml,
    to_bool,
    normalize_roi,
    read_ai_startup_state,
    should_enable_stream_ai
    )

# =========================================================
# 配置路径
# =========================================================

AI_CONFIG_PATH = Path("/home/jetson/code/Cam_flaskvue/app/AIConfig.yaml")

# =========================================================
# 推流配置
# =========================================================

FFMPEG_EXE = "ffmpeg"
URL_LOW = "rtmp://127.0.0.1:1935/cam_low"
URL_HIGH = "rtmp://127.0.0.1:1935/cam_high"

# =========================================================
# 摄像头硬件参数
# =========================================================

CAMERA_ID = 0
ORI_WIDTH = 2592
ORI_HEIGHT = 1944
ORI_FPS = 30

cam_manager = CamManager(
    camera_id=CAMERA_ID,
    width=ORI_WIDTH,
    height=ORI_HEIGHT,
    fps=ORI_FPS,
)

AI_INFER_ENABLE, AI_INFER_TARGET = read_ai_startup_state(AI_CONFIG_PATH)

# =========================================================
# 两路推流
# =========================================================

stream_high = CamStream(
    name="cam_high",
    url=URL_HIGH,
    ffmpeg_exe=FFMPEG_EXE,
    width=1280,
    height=720,
    fps=30,
    enable_infer=should_enable_stream_ai(
        "cam_high",
        AI_INFER_ENABLE,
        AI_INFER_TARGET
    ),
    ai_config_path=str(AI_CONFIG_PATH),
)

stream_low = CamStream(
    name="cam_low",
    url=URL_LOW,
    ffmpeg_exe=FFMPEG_EXE,
    width=640,
    height=480,
    fps=15,
    enable_infer=should_enable_stream_ai(
        "cam_low",
        AI_INFER_ENABLE,
        AI_INFER_TARGET
    ),
    ai_config_path=str(AI_CONFIG_PATH),
)

# stream_high = CamStream(
#     name="cam_high",
#     url=URL_HIGH,
#     ffmpeg_exe=FFMPEG_EXE,
#     width=1280,
#     height=720,
#     fps=30,
#     enable_infer=False,
#     ai_config_path=str(AI_CONFIG_PATH),
# )

# stream_low = CamStream(
#     name="cam_low",
#     url=URL_LOW,
#     ffmpeg_exe=FFMPEG_EXE,
#     width=640,
#     height=480,
#     fps=15,
#     enable_infer=False,
#     ai_config_path=str(AI_CONFIG_PATH),
# )

cam_manager.add_worker(stream_high)
cam_manager.add_worker(stream_low)

# 全局启动推流
cam_manager.start()


def get_target_streams(target="high"):
    target = str(target or "high").lower()

    if target == "high":
        return [stream_high]

    if target == "low":
        return [stream_low]

    if target == "all":
        return [stream_high, stream_low]

    raise ValueError("target 必须是 high、low 或 all")


def set_infer_enable(enable, target="high"):
    changed = []

    for stream in get_target_streams(target):
        stream.set_infer_enable(
            enable=enable,
            reload_when_enable=True,
            release_when_disable=True,
        )
        changed.append(stream.name)

    return changed

def sync_infer_enable_from_config(cfg=None):
    """
    根据 AIConfig.yaml 中的 model.detect_enable 和 model.infer_target
    同步当前运行中的 AI 推理状态。

    规则：
    1. detect_enable=false：关闭所有流的 AI 推理
    2. detect_enable=true 且 infer_target=high：只开启 high，关闭 low
    3. detect_enable=true 且 infer_target=low：只开启 low，关闭 high
    4. detect_enable=true 且 infer_target=all：两路都开启
    """
    if cfg is None:
        cfg = read_yaml(AI_CONFIG_PATH)

    model_cfg = cfg.get("model", {})
    detect_enable = to_bool(model_cfg.get("detect_enable", False))
    target = str(model_cfg.get("infer_target", "high")).lower()

    if target not in ["high", "low", "all"]:
        raise ValueError("infer_target 必须是 high、low 或 all")

    if detect_enable:
        enabled_stream_names = {
            stream.name for stream in get_target_streams(target)
        }
    else:
        enabled_stream_names = set()

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
                "action": "enable" if new_enable else "disable"
            })

        elif new_enable:
            # 开关没变，但配置参数可能变了，比如阈值、ROI、模型名变了
            stream.reload_ai_config()

            changed.append({
                "name": stream.name,
                "old_enable": old_enable,
                "new_enable": new_enable,
                "action": "reload"
            })

    return changed


def reload_enabled_streams():
    reloaded = []

    for stream in [stream_high, stream_low]:
        if getattr(stream, "enable_infer", False):
            stream.reload_ai_config()
            reloaded.append(stream.name)

    return reloaded
# =========================================================
# 基础接口
# =========================================================

@app.route("/")
def index():
    return jsonify({
        "status": "success",
        "message": "API is running"
    })

# =========================================================
# 推流接口
# =========================================================

@app.route("/api/stream/start", methods=["POST", "GET"])
def start_streams():
    try:
        cam_manager.start()
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
        cam_manager.stop()
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
        cam_manager.set_exposure(value)

        return jsonify({
            "status": "success",
            "message": f"曝光已设置为: {value}"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"设置曝光失败: {e}"
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

        for stream in get_target_streams(target):
            stream.set_resolution(width, height)

        return jsonify({
            "status": "success",
            "message": f"分辨率已设置为 {width}x{height}, target={target}"
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"设置分辨率失败: {e}"
        }), 400


@app.route("/api/stream/fps", methods=["POST"])
def set_fps():
    data = request.get_json(silent=True) or {}

    if "fps" not in data:
        return jsonify({
            "status": "error",
            "message": "缺少 fps 参数"
        }), 400

    try:
        fps = int(data["fps"])
        target = data.get("target", "high")

        for stream in get_target_streams(target):
            stream.set_fps(fps)

        return jsonify({
            "status": "success",
            "message": f"FPS 已设置为 {fps}, target={target}"
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
        cfg = read_yaml(AI_CONFIG_PATH)
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
            model_cfg["model_name"] = data["detectionModel"]

        if "detectionThreshold" in data:
            model_cfg["conf_thres"] = float(data["detectionThreshold"])

        if "overlapRate" in data:
            model_cfg["iou_thres"] = float(data["overlapRate"])

        write_yaml(cfg, file_path=AI_CONFIG_PATH)

        changed_streams = sync_infer_enable_from_config(cfg)

        # changed_streams = set_infer_enable(
        #     enable=detect_enable,
        #     target=target
        # )

        return jsonify({
            "status": "success",
            "message": "检测设置已更新",
            "data": {
                "detect_enable": detect_enable,
                "target": target,
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
        cfg = read_yaml(AI_CONFIG_PATH)
        rois = cfg.get("model", {}).get("rois", [])

        return jsonify({
            "status": "success",
            "rois": rois
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"获取检测区域失败: {e}",
            "rois": []
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

        if not isinstance(raw_rois, list):
            raise ValueError("rois 必须是数组")

        cfg = read_yaml(AI_CONFIG_PATH)
        model_cfg = cfg.setdefault("model", {})
        model_cfg["rois"] = [
            normalize_roi(roi, index)
            for index, roi in enumerate(raw_rois)
        ]

        write_yaml(cfg, file_path=AI_CONFIG_PATH)

        reloaded = sync_infer_enable_from_config(cfg)

        return jsonify({
            "status": "success",
            "message": "检测区域已保存",
            "data": {
                "roi_count": len(model_cfg["rois"]),
                "reloaded": reloaded
            }
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
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
    return render_template("404.html"), 404