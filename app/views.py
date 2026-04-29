"""
Flask Documentation:     https://flask.palletsprojects.com/
Jinja2 Documentation:    https://jinja.palletsprojects.com/
Werkzeug Documentation:  https://werkzeug.palletsprojects.com/
This file creates your application.
"""

from app import app
from flask import render_template, request, jsonify, send_file
from app.Cam.CamStream import CamStream
from app.Cam.CamManager import CamManager
import os

FFMPEG_EXE = "ffmpeg"
URL_LOW = "rtmp://127.0.0.1:1935/cam_low"
URL_HIGH = "rtmp://127.0.0.1:1935/cam_high"

# 摄像头硬件层读取参数设置
ORI_WIDTH = 2592
ORI_HEIGHT = 1944
ORI_FPS = 30
CAMERA_ID = 0
cam_manager = CamManager(camera_id=CAMERA_ID, width=ORI_WIDTH, height=ORI_HEIGHT, fps=ORI_FPS)

# 两路分流
HIGH_WIDTH, HIGH_HEIGHT = 1280, 720
LOW_WIDTH, LOW_HEIGHT = 640, 480
HIGH_FPS, LOW_FPS = 30, 15
stream_high = CamStream(
        name="cam_high",
        url=URL_HIGH, 
        ffmpeg_exe=FFMPEG_EXE, 
        width=HIGH_WIDTH, 
        height=HIGH_HEIGHT, 
        fps=HIGH_FPS
    )
stream_low = CamStream(
        name="cam_low",  
        url=URL_LOW, 
        ffmpeg_exe=FFMPEG_EXE, 
        width=LOW_WIDTH, 
        height=LOW_HEIGHT, 
        fps=LOW_FPS
    )
# CamStream添加到CamManager类统一管理
cam_manager.add_worker(stream_high)
cam_manager.add_worker(stream_low)


cam_manager.start() # 全局启动推流 [不用单独启动]

@app.route('/')
def index():
    return jsonify(message="This is the beginning of our API")

@app.route('/api/stream/start', methods=['POST', 'GET'])
def start_streams():
    """启动两路推流"""
    try:
        cam_manager.start()
        return jsonify({
            "status": "success", 
            "message": "双路推流请求已执行 (1280x720 & 1920x1080)"
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"启动推流失败: {str(e)}"
        }), 500
        
@app.route('/api/stream/stop', methods=['POST', 'GET'])
def stop_streams():
    """停止两路推流"""
    try:
        cam_manager.stop()
        return jsonify({
            "status": "success", 
            "message": "双路推流已停止"
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"停止推流失败: {str(e)}"
        }), 500
        
@app.route('/api/stream/exposure', methods=['POST'])
def set_exposure():
    """
    设置曝光参数 (硬件全局生效)
    接收 JSON 格式: {"value": 0} 
    - value: 0 为自动，-1 ~ -13 为手动
    """
    data = request.get_json()
    if data is None or 'value' not in data:
        return jsonify({"status": "error", "message": "缺少 value 参数"}), 400
    
    try:
        val = int(data['value'])
        # 曝光是硬件属性，直接通过 cam_manager 修改，对所有流同步生效
        cam_manager.set_exposure(val)
            
        return jsonify({
            "status": "success", 
            "message": f"全局硬件曝光已设置为: {val} (0为自动)"
        })
    except ValueError:
        return jsonify({"status": "error", "message": "value 必须是整数"}), 400

@app.route('/api/stream/resolution', methods=['POST'])
def set_resolution():
    """
    设置特定流的分辨率 (软件缩放/编码生效)
    接收 JSON 格式: {"width": 1280, "height": 720, "target": "high"}
    - target: "low", "high", "all"
    """
    data = request.get_json()
    if data is None or 'width' not in data or 'height' not in data:
        return jsonify({"status": "error", "message": "缺少 width 或 height 参数"}), 400
    
    try:
        w, h = int(data['width']), int(data['height'])
        target = data.get('target', 'high').lower() 
        
        if target in ['low', 'all']:
            stream_low.set_resolution(w, h)
        if target in ['high', 'all']:
            stream_high.set_resolution(w, h)
            
        return jsonify({
            "status": "success", 
            "message": f"分辨率切换请求已执行: {w}x{h} (目标: {target})"
        })
    except ValueError:
        return jsonify({"status": "error", "message": "参数必须是整数"}), 400
    
@app.route('/api/stream/fps', methods=['POST'])
def set_fps():
    """
    设置特定流的帧率 (FFmpeg 编码帧率)
    接收 JSON 格式: {"fps": 30, "target": "high"}
    - target: "low", "high", "all"
    """
    data = request.get_json()
    if data is None or 'fps' not in data:
        return jsonify({"status": "error", "message": "缺少 fps 参数"}), 400
    
    try:
        new_fps = int(data['fps'])
        target = data.get('target', 'high').lower()
        
        # 注意：此操作会导致对应的 FFmpeg 进程重启以应用新帧率
        if target in ['low', 'all']:
            stream_low.set_fps(new_fps)
        if target in ['high', 'all']:
            stream_high.set_fps(new_fps)
            
        return jsonify({
            "status": "success", 
            "message": f"帧率修改请求已执行: {new_fps} (目标: {target})"
        })
    except ValueError:
        return jsonify({"status": "error", "message": "fps 必须是整数"}), 400

###
# The functions below should be applicable to all Flask apps.
###

# Here we define a function to collect form errors from Flask-WTF
# which we can later use
def form_errors(form):
    error_messages = []
    """Collects form errors"""
    for field, errors in form.errors.items():
        for error in errors:
            message = u"Error in the %s field - %s" % (
                    getattr(form, field).label.text,
                    error
                )
            error_messages.append(message)

    return error_messages

@app.route('/<file_name>.txt')
def send_text_file(file_name):
    """Send your static text file."""
    file_dot_text = file_name + '.txt'
    return app.send_static_file(file_dot_text)


@app.after_request
def add_header(response):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also tell the browser not to cache the rendered page. If we wanted
    to we could change max-age to 600 seconds which would be 10 minutes.
    """
    response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
    response.headers['Cache-Control'] = 'public, max-age=0'
    return response


@app.errorhandler(404)
def page_not_found(error):
    """Custom 404 page."""
    return render_template('404.html'), 404