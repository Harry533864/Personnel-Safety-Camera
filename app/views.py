"""
Flask Documentation:     https://flask.palletsprojects.com/
Jinja2 Documentation:    https://jinja.palletsprojects.com/
Werkzeug Documentation:  https://werkzeug.palletsprojects.com/
This file creates your application.
"""

from app import app
from flask import render_template, request, jsonify, send_file
import os

from Cam.CamStream import CamStream
FFMPEG_EXE = "D:/CodeSoftware/VisualStudioCode/VsCodeProject/info3180-vuejs-flask-starter/app/Cam/ffmpeg/bin/ffmpeg.exe"
URL_LOW = "rtmp://127.0.0.1:1935/cam_low"
URL_HIGH = "rtmp://127.0.0.1:1935/cam_high"
stream_low = CamStream(url=URL_LOW, ffmpeg_exe=FFMPEG_EXE, width=1280, height=720, name="cam_low")
stream_high = CamStream(url=URL_HIGH, ffmpeg_exe=FFMPEG_EXE, width=1920, height=1080, name="cam_high")


@app.route('/')
def index():
    return jsonify(message="This is the beginning of our API")

@app.route('/api/stream/start', methods=['POST', 'GET'])
def start_streams():
    """启动两路推流"""
    try:
        stream_low.start()
        stream_high.start()
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
        stream_low.stop()
        stream_high.stop()
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
    设置曝光参数
    接收 JSON 格式: {"value": 0, "target": "all"} 
    - value: 0 为自动，-1 ~ -13 为手动
    - target: 可选值为 "low", "high", "all" (默认 "high")
    """
    data = request.get_json()
    
    if data is None or 'value' not in data:
        return jsonify({"status": "error", "message": "缺少 value 参数"}), 400
    
    try:
        val = int(data['value'])
        target = data.get('target', 'high').lower()
        
        # 根据 target 决定作用于哪个实例
        if target in ['low', 'all']:
            stream_low.set_exposure(val)
        if target in ['high', 'all']:
            stream_high.set_exposure(val)
            
        return jsonify({
            "status": "success", 
            "message": f"曝光请求已接收: {val} (作用目标: {target})"
        })
    except ValueError:
        return jsonify({"status": "error", "message": "value 必须是整数"}), 400

@app.route('/api/stream/resolution', methods=['POST'])
def set_resolution():
    """
    设置分辨率
    接收 JSON 格式: {"width": 1920, "height": 1080, "target": "high"}
    - target: 可选值为 "low", "high", "all" (默认 "high")
    """
    data = request.get_json()
    
    if data is None or 'width' not in data or 'height' not in data:
        return jsonify({"status": "error", "message": "缺少 width 或 height 参数"}), 400
    
    try:
        w = int(data['width'])
        h = int(data['height'])
        # 分辨率修改通常针对特定流，这里默认只改高画质流
        target = data.get('target', 'high').lower() 
        
        if target in ['low', 'all']:
            stream_low.set_resolution(w, h)
        if target in ['high', 'all']:
            stream_high.set_resolution(w, h)
            
        return jsonify({
            "status": "success", 
            "message": f"分辨率切换请求已接收: {w}x{h} (作用目标: {target})"
        })
    except ValueError:
        return jsonify({"status": "error", "message": "width 和 height 必须是整数"}), 400

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