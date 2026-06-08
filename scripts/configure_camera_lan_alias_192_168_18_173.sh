#!/usr/bin/env bash
set -euo pipefail

CONNECTION_NAME="${CONNECTION_NAME:-Wired connection 1}"
DEVICE_NAME="${DEVICE_NAME:-eth0}"
PRIMARY_IP="${PRIMARY_IP:-10.10.10.2/24}"
LAN_IP="${LAN_IP:-192.168.18.173/24}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Please run with sudo on the camera:"
  echo "  sudo $0"
  exit 1
fi

if findmnt -n -O ro / >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Root filesystem is read-only, so NetworkManager cannot persist this change.

Run this once, reboot, then run this script again:
  sudo /opt/baumer-vax/ro/configure-rw-boot.sh
  sudo reboot
EOF
  exit 2
fi

nmcli connection modify "$CONNECTION_NAME" \
  ipv4.method manual \
  ipv4.addresses "$PRIMARY_IP,$LAN_IP" \
  ipv4.gateway "" \
  ipv4.dns ""

nmcli device reapply "$DEVICE_NAME" || nmcli connection up "$CONNECTION_NAME"

echo "Camera LAN addresses configured:"
ip -br addr show "$DEVICE_NAME"
nmcli -f connection.id,ipv4.method,ipv4.addresses,ipv4.gateway connection show "$CONNECTION_NAME"
