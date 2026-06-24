#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
VENV_DIR="${VENV_DIR:-$REPO_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
FLASK_PORT="${FLASK_PORT:-5000}"
STREAM_PORT="${STREAM_PORT:-8889}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
CAMERA_SOURCE="${CAMERA_SOURCE:-usb}"
CAMERA_DEVICE="${CAMERA_DEVICE:-/dev/video0}"
CAMERA_WAIT_SECONDS="${CAMERA_WAIT_SECONDS:-45}"
CAMERA_WIDTH="${CAMERA_WIDTH:-1920}"
CAMERA_HEIGHT="${CAMERA_HEIGHT:-1080}"
CAMERA_FPS="${CAMERA_FPS:-60}"
CAMERA_FOURCC="${CAMERA_FOURCC:-MJPG}"
USB_CAMERA_DEVICE="${USB_CAMERA_DEVICE:-$CAMERA_DEVICE}"
USB_CAMERA_WIDTH="${USB_CAMERA_WIDTH:-$CAMERA_WIDTH}"
USB_CAMERA_HEIGHT="${USB_CAMERA_HEIGHT:-$CAMERA_HEIGHT}"
USB_CAMERA_FPS="${USB_CAMERA_FPS:-$CAMERA_FPS}"
USB_CAMERA_FOURCC="${USB_CAMERA_FOURCC:-$CAMERA_FOURCC}"
USB_CAMERA_DECODER="${USB_CAMERA_DECODER:-auto}"
CSI_SENSOR_ID="${CSI_SENSOR_ID:-0}"
CSI_FLIP_METHOD="${CSI_FLIP_METHOD:-0}"
CSI_CAMERA_WIDTH="${CSI_CAMERA_WIDTH:-1920}"
CSI_CAMERA_HEIGHT="${CSI_CAMERA_HEIGHT:-1080}"
CSI_CAMERA_FPS="${CSI_CAMERA_FPS:-30}"
CSI_READY_DEVICE="${CSI_READY_DEVICE:-/dev/media0}"
CSI_DIRECT_STREAM="${CSI_DIRECT_STREAM:-0}"
CSI_DIRECT_RTMP_URL="${CSI_DIRECT_RTMP_URL:-rtmp://127.0.0.1:1935/cam_high}"
CSI_DIRECT_BITRATE_KBPS="${CSI_DIRECT_BITRATE_KBPS:-15000}"
CSI_DIRECT_KEY_INT="${CSI_DIRECT_KEY_INT:-10}"
CSI_DIRECT_VBV_MS="${CSI_DIRECT_VBV_MS:-100}"
STREAM_HIGH_PUBLISH="${STREAM_HIGH_PUBLISH:-1}"
STREAM_HIGH_RECORD="${STREAM_HIGH_RECORD:-1}"
STREAM_HIGH_WIDTH="${STREAM_HIGH_WIDTH:-}"
STREAM_HIGH_HEIGHT="${STREAM_HIGH_HEIGHT:-}"
STREAM_HIGH_FPS="${STREAM_HIGH_FPS:-}"
STREAM_ENCODER="${STREAM_ENCODER:-auto}"
STREAM_OPENH264_THREADS="${STREAM_OPENH264_THREADS:-4}"
STREAM_X264_THREADS="${STREAM_X264_THREADS:-0}"
STREAM_X264_SLICED_THREADS="${STREAM_X264_SLICED_THREADS:-0}"
INSTALL_APT="${INSTALL_APT:-0}"
INSTALL_SYSTEMD="${INSTALL_SYSTEMD:-0}"
RUN_NOW="${RUN_NOW:-0}"
START_FRONTEND="${START_FRONTEND:-0}"
REQUIRE_AI="${REQUIRE_AI:-1}"
RUN_USER="${RUN_USER:-${SUDO_USER:-$(id -un)}}"

cd "$REPO_DIR"

log() {
  printf '[bootstrap] %s\n' "$*"
}

fail() {
  printf '[bootstrap] ERROR: %s\n' "$*" >&2
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

detect_host_ip() {
  if [[ -n "${BACKEND_HOST:-}" ]]; then
    printf '%s\n' "$BACKEND_HOST"
    return
  fi

  local ip=""
  if have_cmd hostname; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi
  printf '%s\n' "${ip:-127.0.0.1}"
}

if [[ "$INSTALL_APT" == "1" ]]; then
  have_cmd sudo || fail "sudo is required when INSTALL_APT=1"
  log "Installing common system packages"
  sudo apt-get update
  sudo apt-get install -y \
    python3-venv python3-pip \
    nodejs npm \
    v4l-utils gstreamer1.0-tools
fi

have_cmd "$PYTHON_BIN" || fail "Python command not found: $PYTHON_BIN"
have_cmd npm || fail "npm not found. Run with INSTALL_APT=1 or install Node.js/npm first."

log "Preparing runtime directories"
mkdir -p logs outputs inference/configs/runtime
chmod +x scripts/*.sh
chmod +x app/Cam/mediamtx/mediamtx || true

[[ -f app/AIConfig.yaml ]] || fail "Missing app/AIConfig.yaml"
[[ -f inference/models/yolo11n_person.onnx ]] || fail "Missing inference/models/yolo11n_person.onnx"
[[ -f inference/models/yolo11n_person.engine ]] || fail "Missing inference/models/yolo11n_person.engine"
[[ -x app/Cam/mediamtx/mediamtx ]] || fail "MediaMTX is missing or not executable"

BACKEND_HOST_RESOLVED="$(detect_host_ip)"
if [[ ! -f .env ]]; then
  log "Creating .env for host $BACKEND_HOST_RESOLVED"
  cat > .env <<EOF
FLASK_DEBUG=False
FLASK_RUN_HOST=$FLASK_HOST
FLASK_RUN_PORT=$FLASK_PORT
SECRET_KEY=
DATABASE_URL=sqlite:///app.db

VITE_FLASK_BACKEND_URL=http://$BACKEND_HOST_RESOLVED:$FLASK_PORT
VITE_VIDEO_STREAM_URL=http://$BACKEND_HOST_RESOLVED:$STREAM_PORT
EOF
else
  log ".env already exists; leaving it unchanged"
fi

log "Creating Python venv with system site packages: $VENV_DIR"
"$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install -r requirements.txt

log "Installing frontend dependencies with npm ci"
npm ci

log "Checking Python runtime imports"
REQUIRE_AI="$REQUIRE_AI" "$VENV_DIR/bin/python" - <<'PY'
import importlib
import os
import sys

required = [
    "flask",
    "flask_cors",
    "jwt",
    "dotenv",
    "numpy",
    "yaml",
    "ruamel.yaml",
]
optional_ai = ["cv2", "torch", "tensorrt"]
failed = []

for name in required:
    try:
        importlib.import_module(name)
    except Exception as exc:
        failed.append(f"{name}: {exc}")

if failed:
    print("Missing required Python modules:", file=sys.stderr)
    for item in failed:
        print(f"  - {item}", file=sys.stderr)
    raise SystemExit(1)

ai_failed = []
for name in optional_ai:
    try:
        importlib.import_module(name)
    except Exception as exc:
        ai_failed.append(f"{name}: {exc}")

if ai_failed:
    message = "AI runtime modules are not fully available:\n" + "\n".join(f"  - {item}" for item in ai_failed)
    if os.environ.get("REQUIRE_AI", "1") == "1":
        print(message, file=sys.stderr)
        raise SystemExit(1)
    print(message)
PY

if [[ "$INSTALL_SYSTEMD" == "1" ]]; then
  have_cmd sudo || fail "sudo is required when INSTALL_SYSTEMD=1"
  log "Installing and starting systemd services"
  sudo \
    REPO_DIR="$REPO_DIR" \
    RUN_USER="$RUN_USER" \
    PYTHON_BIN="$VENV_DIR/bin/python" \
    FLASK_HOST="$FLASK_HOST" \
    FLASK_PORT="$FLASK_PORT" \
    CAMERA_SOURCE="$CAMERA_SOURCE" \
    CAMERA_DEVICE="$CAMERA_DEVICE" \
    CAMERA_WAIT_SECONDS="$CAMERA_WAIT_SECONDS" \
    CAMERA_WIDTH="$CAMERA_WIDTH" \
    CAMERA_HEIGHT="$CAMERA_HEIGHT" \
    CAMERA_FPS="$CAMERA_FPS" \
    CAMERA_FOURCC="$CAMERA_FOURCC" \
    USB_CAMERA_DEVICE="$USB_CAMERA_DEVICE" \
    USB_CAMERA_WIDTH="$USB_CAMERA_WIDTH" \
    USB_CAMERA_HEIGHT="$USB_CAMERA_HEIGHT" \
    USB_CAMERA_FPS="$USB_CAMERA_FPS" \
    USB_CAMERA_FOURCC="$USB_CAMERA_FOURCC" \
    USB_CAMERA_DECODER="$USB_CAMERA_DECODER" \
    CSI_SENSOR_ID="$CSI_SENSOR_ID" \
    CSI_FLIP_METHOD="$CSI_FLIP_METHOD" \
    CSI_CAMERA_WIDTH="$CSI_CAMERA_WIDTH" \
    CSI_CAMERA_HEIGHT="$CSI_CAMERA_HEIGHT" \
    CSI_CAMERA_FPS="$CSI_CAMERA_FPS" \
    CSI_READY_DEVICE="$CSI_READY_DEVICE" \
    CSI_DIRECT_STREAM="$CSI_DIRECT_STREAM" \
    CSI_DIRECT_RTMP_URL="$CSI_DIRECT_RTMP_URL" \
    CSI_DIRECT_BITRATE_KBPS="$CSI_DIRECT_BITRATE_KBPS" \
    CSI_DIRECT_KEY_INT="$CSI_DIRECT_KEY_INT" \
    CSI_DIRECT_VBV_MS="$CSI_DIRECT_VBV_MS" \
    STREAM_HIGH_PUBLISH="$STREAM_HIGH_PUBLISH" \
    STREAM_HIGH_RECORD="$STREAM_HIGH_RECORD" \
    STREAM_HIGH_WIDTH="$STREAM_HIGH_WIDTH" \
    STREAM_HIGH_HEIGHT="$STREAM_HIGH_HEIGHT" \
    STREAM_HIGH_FPS="$STREAM_HIGH_FPS" \
    STREAM_ENCODER="$STREAM_ENCODER" \
    STREAM_OPENH264_THREADS="$STREAM_OPENH264_THREADS" \
    STREAM_X264_THREADS="$STREAM_X264_THREADS" \
    STREAM_X264_SLICED_THREADS="$STREAM_X264_SLICED_THREADS" \
    bash scripts/install_systemd_services.sh
fi

if [[ "$RUN_NOW" == "1" ]]; then
  log "Starting backend stack"
  REPO_DIR="$REPO_DIR" \
    PYTHON_BIN="$VENV_DIR/bin/python" \
    FLASK_HOST="$FLASK_HOST" \
    FLASK_PORT="$FLASK_PORT" \
    CAM_AUTO_START=1 \
    CAMERA_SOURCE="$CAMERA_SOURCE" \
    CAMERA_DEVICE="$CAMERA_DEVICE" \
    CAMERA_WAIT_SECONDS="$CAMERA_WAIT_SECONDS" \
    CAMERA_WIDTH="$CAMERA_WIDTH" \
    CAMERA_HEIGHT="$CAMERA_HEIGHT" \
    CAMERA_FPS="$CAMERA_FPS" \
    CAMERA_FOURCC="$CAMERA_FOURCC" \
    USB_CAMERA_DEVICE="$USB_CAMERA_DEVICE" \
    USB_CAMERA_WIDTH="$USB_CAMERA_WIDTH" \
    USB_CAMERA_HEIGHT="$USB_CAMERA_HEIGHT" \
    USB_CAMERA_FPS="$USB_CAMERA_FPS" \
    USB_CAMERA_FOURCC="$USB_CAMERA_FOURCC" \
    USB_CAMERA_DECODER="$USB_CAMERA_DECODER" \
    CSI_SENSOR_ID="$CSI_SENSOR_ID" \
    CSI_FLIP_METHOD="$CSI_FLIP_METHOD" \
    CSI_CAMERA_WIDTH="$CSI_CAMERA_WIDTH" \
    CSI_CAMERA_HEIGHT="$CSI_CAMERA_HEIGHT" \
    CSI_CAMERA_FPS="$CSI_CAMERA_FPS" \
    CSI_READY_DEVICE="$CSI_READY_DEVICE" \
    CSI_DIRECT_STREAM="$CSI_DIRECT_STREAM" \
    CSI_DIRECT_RTMP_URL="$CSI_DIRECT_RTMP_URL" \
    CSI_DIRECT_BITRATE_KBPS="$CSI_DIRECT_BITRATE_KBPS" \
    CSI_DIRECT_KEY_INT="$CSI_DIRECT_KEY_INT" \
    CSI_DIRECT_VBV_MS="$CSI_DIRECT_VBV_MS" \
    STREAM_HIGH_PUBLISH="$STREAM_HIGH_PUBLISH" \
    STREAM_HIGH_RECORD="$STREAM_HIGH_RECORD" \
    STREAM_HIGH_WIDTH="$STREAM_HIGH_WIDTH" \
    STREAM_HIGH_HEIGHT="$STREAM_HIGH_HEIGHT" \
    STREAM_HIGH_FPS="$STREAM_HIGH_FPS" \
    STREAM_ENCODER="$STREAM_ENCODER" \
    STREAM_OPENH264_THREADS="$STREAM_OPENH264_THREADS" \
    STREAM_X264_THREADS="$STREAM_X264_THREADS" \
    STREAM_X264_SLICED_THREADS="$STREAM_X264_SLICED_THREADS" \
    bash scripts/start_backend_stack.sh

  if [[ "$START_FRONTEND" == "1" ]]; then
    log "Starting Vite frontend on port $FRONTEND_PORT"
    nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" \
      > logs/vite.out.log \
      2> logs/vite.err.log &
    log "Frontend pid=$!"
  fi
fi

cat <<EOF

Jetson bootstrap complete.

Backend API:
  http://$BACKEND_HOST_RESOLVED:$FLASK_PORT/api/runtime/status

WebRTC server:
  http://$BACKEND_HOST_RESOLVED:$STREAM_PORT

Run once without systemd:
  RUN_NOW=1 START_FRONTEND=1 bash scripts/bootstrap_jetson.sh

Install boot services:
  INSTALL_SYSTEMD=1 bash scripts/bootstrap_jetson.sh

Factory check:
  bash scripts/factory_readiness_check.sh
EOF
