#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/jetson/code/Cam_flaskvue}"
RUN_USER="${RUN_USER:-${SUDO_USER:-jetson}}"
FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
FLASK_PORT="${FLASK_PORT:-5000}"
CAMERA_DEVICE="${CAMERA_DEVICE:-/dev/video0}"
CAMERA_WAIT_SECONDS="${CAMERA_WAIT_SECONDS:-45}"
CAMERA_WIDTH="${CAMERA_WIDTH:-1920}"
CAMERA_HEIGHT="${CAMERA_HEIGHT:-1080}"
CAMERA_FPS="${CAMERA_FPS:-60}"
CAM_CAPTURE_BACKEND="${CAM_CAPTURE_BACKEND:-v4l2}"
BAUMER_PIXEL_FORMAT="${BAUMER_PIXEL_FORMAT:-BGR8}"
BAUMER_CONNECT_RETRIES="${BAUMER_CONNECT_RETRIES:-3}"
BAUMER_BRIGHTNESS_AUTO_NOMINAL="${BAUMER_BRIGHTNESS_AUTO_NOMINAL:-28}"
BAUMER_BRIGHTNESS_AUTO_PRIORITY="${BAUMER_BRIGHTNESS_AUTO_PRIORITY:-ExposureAuto}"
BAUMER_EXPOSURE_AUTO_MAX_US="${BAUMER_EXPOSURE_AUTO_MAX_US:-12000}"
BAUMER_GAIN_AUTO_MAX="${BAUMER_GAIN_AUTO_MAX:-32}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
INSTALL_DIR="${INSTALL_DIR:-/etc/systemd/system}"
DISABLE_CRON_AUTOSTART="${DISABLE_CRON_AUTOSTART:-1}"
STOP_LEGACY_STACK="${STOP_LEGACY_STACK:-1}"
CAM_ACCESS_LOG="${CAM_ACCESS_LOG:-0}"
CAM_LOG_LEVEL="${CAM_LOG_LEVEL:-INFO}"
CAM_LOG_MAX_BYTES="${CAM_LOG_MAX_BYTES:-1048576}"
CAM_LOG_BACKUP_COUNT="${CAM_LOG_BACKUP_COUNT:-2}"
CAM_HOME_MIN_FREE_MB="${CAM_HOME_MIN_FREE_MB:-120}"
CAM_HOME_CRITICAL_FREE_MB="${CAM_HOME_CRITICAL_FREE_MB:-60}"
CAM_VIDEO_RETENTION_DAYS="${CAM_VIDEO_RETENTION_DAYS:-7}"

MEDIAMTX_DIR="$REPO_DIR/app/Cam/mediamtx"
MEDIAMTX_BIN="$MEDIAMTX_DIR/mediamtx"
MEDIAMTX_CONFIG="$MEDIAMTX_DIR/mediamtx.yml"
LOG_DIR="$REPO_DIR/logs"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Please run with sudo:"
  echo "  sudo REPO_DIR=$REPO_DIR $0"
  exit 1
fi

if [[ ! -d "$REPO_DIR" ]]; then
  echo "Repository not found: $REPO_DIR" >&2
  exit 1
fi

if [[ ! -x "$MEDIAMTX_BIN" ]]; then
  echo "MediaMTX binary not executable: $MEDIAMTX_BIN" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
chown -R "$RUN_USER":"$RUN_USER" "$LOG_DIR"

cat > "$INSTALL_DIR/asv-mediamtx.service" <<EOF
[Unit]
Description=ASV MediaMTX video server
After=local-fs.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$MEDIAMTX_DIR
ExecStart=$MEDIAMTX_BIN $MEDIAMTX_CONFIG
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > "$INSTALL_DIR/asv-backend.service" <<EOF
[Unit]
Description=ASV Flask backend and camera pipeline
After=local-fs.target asv-mediamtx.service
Wants=asv-mediamtx.service

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$REPO_DIR
Environment=CAM_PROJECT_ROOT=$REPO_DIR
Environment=FLASK_HOST=$FLASK_HOST
Environment=FLASK_PORT=$FLASK_PORT
Environment=CAMERA_DEVICE=$CAMERA_DEVICE
Environment=CAMERA_WAIT_SECONDS=$CAMERA_WAIT_SECONDS
Environment=CAMERA_WIDTH=$CAMERA_WIDTH
Environment=CAMERA_HEIGHT=$CAMERA_HEIGHT
Environment=CAMERA_FPS=$CAMERA_FPS
Environment=CAM_CAPTURE_BACKEND=$CAM_CAPTURE_BACKEND
Environment=BAUMER_PIXEL_FORMAT=$BAUMER_PIXEL_FORMAT
Environment=BAUMER_CONNECT_RETRIES=$BAUMER_CONNECT_RETRIES
Environment=BAUMER_BRIGHTNESS_AUTO_NOMINAL=$BAUMER_BRIGHTNESS_AUTO_NOMINAL
Environment=BAUMER_BRIGHTNESS_AUTO_PRIORITY=$BAUMER_BRIGHTNESS_AUTO_PRIORITY
Environment=BAUMER_EXPOSURE_AUTO_MAX_US=$BAUMER_EXPOSURE_AUTO_MAX_US
Environment=BAUMER_GAIN_AUTO_MAX=$BAUMER_GAIN_AUTO_MAX
Environment=CAM_AUTO_START=1
Environment=CAM_ACCESS_LOG=$CAM_ACCESS_LOG
Environment=CAM_LOG_LEVEL=$CAM_LOG_LEVEL
Environment=CAM_LOG_MAX_BYTES=$CAM_LOG_MAX_BYTES
Environment=CAM_LOG_BACKUP_COUNT=$CAM_LOG_BACKUP_COUNT
Environment=CAM_HOME_MIN_FREE_MB=$CAM_HOME_MIN_FREE_MB
Environment=CAM_HOME_CRITICAL_FREE_MB=$CAM_HOME_CRITICAL_FREE_MB
Environment=CAM_VIDEO_RETENTION_DAYS=$CAM_VIDEO_RETENTION_DAYS
Environment=FLASK_DEBUG=0
Environment=PYTHONUNBUFFERED=1
Environment=PYTHON_BIN=$PYTHON_BIN
ExecStartPre=/bin/sh -c 'if [ -x "$REPO_DIR/scripts/baumer_storage_guard.sh" ]; then "$REPO_DIR/scripts/baumer_storage_guard.sh" --service-start; fi'
ExecStartPre=/bin/sh -c 'i=0; while [ ! -e "\$CAMERA_DEVICE" ] && [ "\$i" -lt "\$CAMERA_WAIT_SECONDS" ]; do i=\$((i+1)); sleep 1; done; exit 0'
ExecStart=/bin/sh -c 'if command -v gunicorn >/dev/null 2>&1; then exec gunicorn --workers 1 --threads 4 --bind "\$FLASK_HOST:\$FLASK_PORT" app:app; else exec "\$PYTHON_BIN" -m flask --app app run --host="\$FLASK_HOST" --port="\$FLASK_PORT"; fi'
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > "$INSTALL_DIR/asv-storage-guard.service" <<EOF
[Unit]
Description=ASV camera storage guard

[Service]
Type=oneshot
User=$RUN_USER
WorkingDirectory=$REPO_DIR
Environment=CAM_PROJECT_ROOT=$REPO_DIR
Environment=CAM_LOG_MAX_BYTES=$CAM_LOG_MAX_BYTES
Environment=CAM_LOG_BACKUP_COUNT=$CAM_LOG_BACKUP_COUNT
Environment=CAM_HOME_MIN_FREE_MB=$CAM_HOME_MIN_FREE_MB
Environment=CAM_HOME_CRITICAL_FREE_MB=$CAM_HOME_CRITICAL_FREE_MB
Environment=CAM_VIDEO_RETENTION_DAYS=$CAM_VIDEO_RETENTION_DAYS
ExecStart=$REPO_DIR/scripts/baumer_storage_guard.sh --timer
StandardOutput=journal
StandardError=journal
EOF

cat > "$INSTALL_DIR/asv-storage-guard.timer" <<EOF
[Unit]
Description=Run ASV camera storage guard periodically

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF

if [[ "$DISABLE_CRON_AUTOSTART" == "1" ]]; then
  tmp_cron="$(mktemp)"
  tmp_cron_filtered="$(mktemp)"
  if crontab -u "$RUN_USER" -l > "$tmp_cron" 2>/dev/null; then
    grep -v "start_backend_stack.sh" "$tmp_cron" > "$tmp_cron_filtered" || true
    crontab -u "$RUN_USER" "$tmp_cron_filtered"
  fi
  rm -f "$tmp_cron" "$tmp_cron_filtered"
fi

if [[ "$STOP_LEGACY_STACK" == "1" ]]; then
  pkill -f "$MEDIAMTX_BIN $MEDIAMTX_CONFIG" 2>/dev/null || true
  pkill -f "python3 -m flask --app app run .*--port=$FLASK_PORT" 2>/dev/null || true
fi

systemctl daemon-reload
systemctl enable asv-mediamtx.service asv-backend.service asv-storage-guard.timer
systemctl restart asv-storage-guard.timer
systemctl start asv-storage-guard.service || true
systemctl restart asv-mediamtx.service
systemctl restart asv-backend.service

echo "Installed systemd services without LAN startup dependency."
echo "  systemctl status asv-mediamtx asv-backend"
echo "  systemctl list-timers asv-storage-guard.timer"
echo "  journalctl -u asv-backend -f"
