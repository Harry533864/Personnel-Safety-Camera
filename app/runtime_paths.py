import os
from pathlib import Path


PROJECT_ROOT = Path(
    os.environ.get("CAM_PROJECT_ROOT", Path(__file__).resolve().parents[1])
).expanduser().resolve()


def _resolve_path(*env_names, default):
    raw_value = None
    for env_name in env_names:
        raw_value = os.environ.get(env_name)
        if raw_value:
            break

    path = Path(raw_value).expanduser() if raw_value else Path(default)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


AI_CONFIG_PATH = _resolve_path(
    "CAM_AI_CONFIG_PATH",
    "AI_CONFIG_PATH",
    default=PROJECT_ROOT / "app" / "AIConfig.yaml",
)

MODEL_FILE_PATH = _resolve_path(
    "CAM_MODEL_DIR",
    "MODEL_FILE_PATH",
    default=PROJECT_ROOT / "inference" / "models",
)

# Keep the historical Jetson layout by default:
# /home/jetson/code/Cam_flaskvue -> /home/jetson/code/video/...
VIDEO_BASE_PATH = _resolve_path(
    "CAM_VIDEO_BASE_DIR",
    "VIDEO_BASE_PATH",
    default=PROJECT_ROOT.parent,
)

LOG_DIR = _resolve_path(
    "CAM_LOG_DIR",
    "LOG_DIR",
    default=PROJECT_ROOT / "logs",
)

CAMERA_CONFIG_PATH = _resolve_path(
    "CAM_CAMERA_CONFIG_PATH",
    "CAMERA_CONFIG_PATH",
    default=PROJECT_ROOT / "app" / "CameraConfig.yaml",
)
