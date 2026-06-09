#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/jetson/code/Cam_flaskvue}"
LOG_DIR="$REPO_DIR/logs"
MEDIAMTX_DIR="$REPO_DIR/app/Cam/mediamtx"
MEDIAMTX_BIN="$MEDIAMTX_DIR/mediamtx"
MEDIAMTX_CONFIG="$MEDIAMTX_DIR/mediamtx.yml"
FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
FLASK_PORT="${FLASK_PORT:-5000}"
CAMERA_SOURCE="${CAMERA_SOURCE:-usb}"
CAMERA_DEVICE="${CAMERA_DEVICE:-/dev/video0}"
CSI_READY_DEVICE="${CSI_READY_DEVICE:-/dev/media0}"
CAMERA_WAIT_SECONDS="${CAMERA_WAIT_SECONDS:-45}"
CSI_DIRECT_STREAM="${CSI_DIRECT_STREAM:-0}"
CSI_DIRECT_RTMP_URL="${CSI_DIRECT_RTMP_URL:-rtmp://127.0.0.1:1935/cam_high}"
CSI_DIRECT_BITRATE_KBPS="${CSI_DIRECT_BITRATE_KBPS:-15000}"
CSI_DIRECT_KEY_INT="${CSI_DIRECT_KEY_INT:-10}"
CSI_DIRECT_VBV_MS="${CSI_DIRECT_VBV_MS:-100}"
STREAM_HIGH_PUBLISH="${STREAM_HIGH_PUBLISH:-1}"
STREAM_HIGH_RECORD="${STREAM_HIGH_RECORD:-1}"
STREAM_X264_THREADS="${STREAM_X264_THREADS:-0}"
STREAM_X264_SLICED_THREADS="${STREAM_X264_SLICED_THREADS:-0}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOCK_FILE="/tmp/cam_backend_stack.lock"

mkdir -p "$LOG_DIR"
cd "$REPO_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date '+%F %T') backend stack start skipped: another start is running" >> "$LOG_DIR/autostart.log"
  exit 0
fi

is_port_listening() {
  local port="$1"
  ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN
}

start_mediamtx() {
  if is_port_listening 8889 || is_port_listening 1935; then
    echo "$(date '+%F %T') mediamtx already running" >> "$LOG_DIR/autostart.log"
    return
  fi

  nohup "$MEDIAMTX_BIN" "$MEDIAMTX_CONFIG" \
    >> "$LOG_DIR/mediamtx.out.log" \
    2>> "$LOG_DIR/mediamtx.err.log" \
    9>&- &

  echo "$(date '+%F %T') mediamtx started pid=$!" >> "$LOG_DIR/autostart.log"
}

start_flask() {
  if is_port_listening "$FLASK_PORT"; then
    echo "$(date '+%F %T') flask backend already running" >> "$LOG_DIR/autostart.log"
    return
  fi

  nohup "$PYTHON_BIN" -m flask --app app run --host="$FLASK_HOST" --port="$FLASK_PORT" \
    >> "$LOG_DIR/flask.out.log" \
    2>> "$LOG_DIR/flask.err.log" \
    9>&- &

  echo "$(date '+%F %T') flask backend started pid=$!" >> "$LOG_DIR/autostart.log"
}

wait_for_camera() {
  local waited=0
  local ready_device="$CAMERA_DEVICE"

  if [[ "$CAMERA_SOURCE" == "csi" ]]; then
    ready_device="$CSI_READY_DEVICE"
  fi

  while [[ ! -e "$ready_device" && "$waited" -lt "$CAMERA_WAIT_SECONDS" ]]; do
    sleep 1
    waited=$((waited + 1))
  done

  if [[ -e "$ready_device" ]]; then
    echo "$(date '+%F %T') camera source=$CAMERA_SOURCE ready: $ready_device waited=${waited}s" >> "$LOG_DIR/autostart.log"
  else
    echo "$(date '+%F %T') camera source=$CAMERA_SOURCE not ready after ${CAMERA_WAIT_SECONDS}s: $ready_device; starting backend anyway" >> "$LOG_DIR/autostart.log"
  fi
}

start_mediamtx
sleep 2
wait_for_camera
start_flask
