#!/usr/bin/env bash
set -euo pipefail

CONNECTION_NAME="${CONNECTION_NAME:-Wired connection 1}"
STATIC_IP="${STATIC_IP:-192.168.18.172/24}"
GATEWAY="${GATEWAY:-192.168.18.1}"
DNS="${DNS:-192.168.18.1,8.8.8.8}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Please run with sudo:"
  echo "  sudo $0"
  exit 1
fi

nmcli connection modify "$CONNECTION_NAME" \
  ipv4.method manual \
  ipv4.addresses "$STATIC_IP" \
  ipv4.gateway "$GATEWAY" \
  ipv4.dns "$DNS" \
  connection.autoconnect yes

nmcli connection down "$CONNECTION_NAME" || true
nmcli connection up "$CONNECTION_NAME"

echo "Network status:"
ip -br addr
ip route
