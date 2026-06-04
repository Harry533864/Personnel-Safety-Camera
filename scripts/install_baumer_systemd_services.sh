#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-/home/baumer/Cam_flaskvue}"
RUN_USER="${RUN_USER:-baumer}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Please run with sudo on the Baumer camera:"
  echo "  sudo REPO_DIR=$REPO_DIR $0"
  exit 1
fi

if findmnt -n -O ro / >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Root filesystem is read-only.

Run this once, reboot, then run this installer again:
  sudo /opt/baumer-vax/ro/configure-rw-boot.sh
  sudo reboot

The camera should return on 10.10.10.2 after the reboot.
EOF
  exit 2
fi

export REPO_DIR
export RUN_USER
export PYTHON_BIN
export CAMERA_DEVICE="${CAMERA_DEVICE:-baumer_neoapi}"
export CAMERA_WAIT_SECONDS="${CAMERA_WAIT_SECONDS:-0}"
export CAM_CAPTURE_BACKEND="${CAM_CAPTURE_BACKEND:-baumer_neoapi}"
export BAUMER_PIXEL_FORMAT="${BAUMER_PIXEL_FORMAT:-BGR8}"
export BAUMER_CONNECT_RETRIES="${BAUMER_CONNECT_RETRIES:-5}"
export CAMERA_WIDTH="${CAMERA_WIDTH:-1920}"
export CAMERA_HEIGHT="${CAMERA_HEIGHT:-1080}"
export CAMERA_FPS="${CAMERA_FPS:-60}"
export FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
export FLASK_PORT="${FLASK_PORT:-5000}"

"$SCRIPT_DIR/install_systemd_services.sh"

cat <<EOF
Baumer backend services installed.

Defaults:
  REPO_DIR=$REPO_DIR
  RUN_USER=$RUN_USER
  CAM_CAPTURE_BACKEND=$CAM_CAPTURE_BACKEND
  CAMERA_WIDTH=${CAMERA_WIDTH}
  CAMERA_HEIGHT=${CAMERA_HEIGHT}
  CAMERA_FPS=${CAMERA_FPS}

After verifying the backend, reboot once more so the vendor read-only mode is restored.
EOF
