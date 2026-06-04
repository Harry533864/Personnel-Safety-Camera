#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/jetson/code/Cam_flaskvue}"
LOG_DIR="$REPO_DIR/logs"
MEDIAMTX_DIR="$REPO_DIR/app/Cam/mediamtx"
MEDIAMTX_BIN="$MEDIAMTX_DIR/mediamtx"
MEDIAMTX_CONFIG="$MEDIAMTX_DIR/mediamtx.yml"
FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
FLASK_PORT="${FLASK_PORT:-5000}"
CAMERA_DEVICE="${CAMERA_DEVICE:-/dev/video0}"
CAMERA_WAIT_SECONDS="${CAMERA_WAIT_SECONDS:-45}"
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

  nohup python3 -m flask --app app run --host="$FLASK_HOST" --port="$FLASK_PORT" \
    >> "$LOG_DIR/flask.out.log" \
    2>> "$LOG_DIR/flask.err.log" \
    9>&- &

  echo "$(date '+%F %T') flask backend started pid=$!" >> "$LOG_DIR/autostart.log"
}

wait_for_camera() {
  local waited=0

  while [[ ! -e "$CAMERA_DEVICE" && "$waited" -lt "$CAMERA_WAIT_SECONDS" ]]; do
    sleep 1
    waited=$((waited + 1))
  done

  if [[ -e "$CAMERA_DEVICE" ]]; then
    echo "$(date '+%F %T') camera device ready: $CAMERA_DEVICE waited=${waited}s" >> "$LOG_DIR/autostart.log"
  else
    echo "$(date '+%F %T') camera device not found after ${CAMERA_WAIT_SECONDS}s: $CAMERA_DEVICE; starting backend anyway" >> "$LOG_DIR/autostart.log"
  fi
}

start_mediamtx
sleep 2
wait_for_camera
start_flask
