SUPPORTED_CAMERA_MODES = {
    (2592, 1944): {"max_fps": 30, "label": "500万全视野"},
    (2048, 1536): {"max_fps": 30, "label": "300万全视野"},
    (2592, 1440): {"max_fps": 30, "label": "宽幅高清"},
    (2304, 1296): {"max_fps": 30, "label": "300万宽幅"},
    (1920, 1080): {"max_fps": 60, "label": "200万高清"},
    (1600, 900): {"max_fps": 60, "label": "高清预览"},
    (1280, 720): {"max_fps": 60, "label": "720P预览"},
    (1024, 576): {"max_fps": 60, "label": "低延迟预览"},
    (640, 360): {"max_fps": 60, "label": "低带宽预览"},
}

HIGH_RES_STREAM_SAMPLE_FPS = 15
HIGH_RES_STREAM_SAMPLE_PIXELS = 1920 * 1080
HIGH_RES_PREVIEW_MAX_WIDTH = 1280


def camera_mode_key(width, height):
    return f"{int(width)}x{int(height)}"


def parse_camera_mode_key(value):
    parts = str(value or "").lower().replace(" ", "").split("x")
    if len(parts) != 2:
        raise ValueError(f"无效分辨率标识: {value}")
    return int(parts[0]), int(parts[1])


def get_supported_resolution_options():
    return [
        {
            "key": camera_mode_key(width, height),
            "width": width,
            "height": height,
            "max_fps": int(meta["max_fps"]),
            "label": meta["label"],
        }
        for (width, height), meta in SUPPORTED_CAMERA_MODES.items()
    ]


def normalize_camera_mode(width, height, fps):
    width = int(width)
    height = int(height)
    fps = int(fps)

    mode = SUPPORTED_CAMERA_MODES.get((width, height))
    if mode is None:
        supported = ", ".join(f"{w}x{h}" for w, h in SUPPORTED_CAMERA_MODES)
        raise ValueError(f"不支持的分辨率 {width}x{height}，可选：{supported}")

    max_fps = int(mode["max_fps"])
    return {
        "width": width,
        "height": height,
        "fps": max(1, min(fps, max_fps)),
        "requested_fps": fps,
        "max_fps": max_fps,
        "fps_adjusted": fps > max_fps,
        "label": mode["label"],
    }


def sample_stream_fps(width, height, fps):
    """Downsample high-resolution preview streams to reduce latency."""
    width = int(width)
    height = int(height)
    fps = max(1, int(fps))
    stream_width = width
    stream_height = height

    if width * height > HIGH_RES_STREAM_SAMPLE_PIXELS:
        sampled_fps = min(fps, HIGH_RES_STREAM_SAMPLE_FPS)
        if width > HIGH_RES_PREVIEW_MAX_WIDTH:
            scale = HIGH_RES_PREVIEW_MAX_WIDTH / width
            stream_width = HIGH_RES_PREVIEW_MAX_WIDTH
            stream_height = max(2, int(round(height * scale / 2) * 2))
    else:
        sampled_fps = fps

    return {
        "width": stream_width,
        "height": stream_height,
        "fps": sampled_fps,
        "source_width": width,
        "source_height": height,
        "requested_fps": fps,
        "sampled": sampled_fps != fps or stream_width != width or stream_height != height,
        "sample_reason": (
            "high_resolution_low_latency"
            if sampled_fps != fps or stream_width != width or stream_height != height
            else ""
        ),
    }
