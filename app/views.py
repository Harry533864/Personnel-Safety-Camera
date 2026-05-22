from pathlib import Path
import shutil

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
MODEL_FILE_PATH = Path("/home/jetson/code/Cam_flaskvue/inference/models")
VIDEO_BASE_PATH = Path("/home/jetson/code")

# =========================================================
# 推流配置
# =========================================================

URL_LOW = "rtmp://127.0.0.1:1935/cam_low"
URL_HIGH = "rtmp://127.0.0.1:1935/cam_high"

# =========================================================
# 摄像头硬件参数
# =========================================================

CAMERA_ID = 0
ORI_WIDTH = 1280
ORI_HEIGHT = 720
ORI_FPS = 60

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
    width=1280,
    height=720,
    fps=30,
    enable_infer=should_enable_stream_ai(
        "cam_high",
        AI_INFER_ENABLE,
        AI_INFER_TARGET
    ),
    ai_config_path=str(AI_CONFIG_PATH),
    enable_record=True, # 高分辨率流默认保存
    video_base_dir=VIDEO_BASE_PATH
)

# stream_low = CamStream(
#     name="cam_low",
#     url=URL_LOW,
#     width=640,
#     height=480,
#     fps=15,
#     enable_infer=should_enable_stream_ai(
#         "cam_low",
#         AI_INFER_ENABLE,
#         AI_INFER_TARGET
#     ),
#     ai_config_path=str(AI_CONFIG_PATH),
#     enable_record=False # 低分辨率流不默认保存
# )

cam_manager.add_worker(stream_high)
# cam_manager.add_worker(stream_low)

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

        # 让硬件管理器修改参数并重启硬件取流
        cam_manager.set_resolution(width, height)

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

    if "value" not in data:
        return jsonify({
            "status": "error",
            "message": "缺少 fps 参数"
        }), 400

    try:
        fps = int(data["value"])
        target = data.get("target", "high")

        # 让硬件管理器修改参数并重启硬件取流
        cam_manager.set_fps(fps)

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
            overlap_thres = float(data["overlapRate"])
            for roi in model_cfg.get("rois", []):
                roi["overlap_thres"] = overlap_thres

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

    # 检查是否有以 .engine 后缀的文件
    if not engine_file.filename.endswith('.engine'):
        return jsonify({"status": "error", "message": "engine_file 必须是 .engine 文件"}), 400
        
    # 检查是否有以 .txt 后缀的文件
    if not txt_file.filename.endswith('.txt'):
        return jsonify({"status": "error", "message": "txt_file 必须是 .txt 文件"}), 400

    try:
        # 2. 读取并检查配置
        cfg = read_yaml(AI_CONFIG_PATH)
        # 如果没有model_names字段则为空列表
        model_names = cfg.get("model_names") or []
        if not isinstance(model_names, list):
            model_names = []

        # 模型名称已存在时返回错误
        if model_name in model_names:
            return jsonify({
                "status": "error",
                "message": f"模型 '{model_name}' 已存在，请使用其他名称"
            }), 400

        # 3. 确定保存路径并创建文件夹
        # /inference/models/<model_name>/
        save_dir = MODEL_FILE_PATH / model_name
        save_dir.mkdir(parents=True, exist_ok=True)

        # 4. 保存并重命名文件
        # /inference/models/<model_name>/<model_name>.engine
        # /inference/models/<model_name>/<model_name>.txt
        engine_path = save_dir / f"{model_name}.engine"
        txt_path = save_dir / f"{model_name}.txt"
        engine_file.save(str(engine_path))
        txt_file.save(str(txt_path))

        # 5. 更新 AIConfig.yaml 中的 model_names 列表字段
        model_names.append(model_name)
        cfg["model_names"] = model_names
        write_yaml(cfg, file_path=AI_CONFIG_PATH)

        return jsonify({
            "status": "success",
            "message": f"模型 '{model_name}' 成功上传并配置",
            "data": {
                "model_name": model_name,
                "engine_path": str(engine_path),
                "txt_path": str(txt_path)
            }
        })

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
        cfg = read_yaml(AI_CONFIG_PATH)
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
        cfg = read_yaml(AI_CONFIG_PATH)
        model_names = cfg.get("model_names") or []
        if not isinstance(model_names, list):
            model_names = []
            
        if model_name not in model_names:
            return jsonify({"status": "error", "message": f"模型 '{model_name}' 不存在"}), 404
            
        # 1. 移除模型配置
        model_names.remove(model_name)
        cfg["model_names"] = model_names
        write_yaml(cfg, file_path=AI_CONFIG_PATH)
        
        # 2. 删除对应的模型文件夹
        model_dir = MODEL_FILE_PATH / model_name
        if model_dir.exists() and model_dir.is_dir():
            shutil.rmtree(str(model_dir))
            
        return jsonify({
            "status": "success",
            "message": f"模型 '{model_name}' 及相关文件删除成功"
        })
        
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

    if gpio_raw is None:
        return jsonify({
            "status": "error",
            "message": "缺少 gpio 参数"
        }), 400

    if level_raw is None:
        return jsonify({
            "status": "error",
            "message": "缺少 output_level 参数"
        }), 400

    try:
        gpio_pins = normalize_gpio_pins(gpio_raw)

        output_level = normalize_gpio_output_level(level_raw)

        duration = float(duration_raw)
        if duration < 0:
            raise ValueError("duration 必须大于等于 0，0 表示一直保持")

        # 如果是整数秒，写入 YAML 时保持为 int，避免 5.0
        if duration.is_integer():
            duration = int(duration)

        cfg = read_yaml(AI_CONFIG_PATH)

        cfg["exception_output"] = {
            "gpio": gpio_pins,
            "output_level": output_level,
            "duration": duration
        }

        write_yaml(cfg, file_path=AI_CONFIG_PATH)

        # 如果推理流运行中，让它重新读取配置
        reloaded = reload_enabled_streams()

        return jsonify({
            "status": "success",
            "message": "异常输出配置已更新",
            "data": {
                "exception_output": cfg["exception_output"],
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
                
            # 读取并重写 YAML 文件
            cfg = read_yaml(AI_CONFIG_PATH)
            record_cfg = cfg.setdefault("record", {})
            record_cfg["duration_min"] = duration_min
            
            write_yaml(cfg, file_path=AI_CONFIG_PATH)
            
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
            cfg = read_yaml(AI_CONFIG_PATH)
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