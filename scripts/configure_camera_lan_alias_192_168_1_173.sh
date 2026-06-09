#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export LAN_IP="${LAN_IP:-192.168.1.173/24}"
exec "$SCRIPT_DIR/configure_camera_lan_alias_192_168_18_173.sh"
