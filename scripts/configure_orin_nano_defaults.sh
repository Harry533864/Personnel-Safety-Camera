#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUN_USER="${RUN_USER:-${SUDO_USER:-wanan}}"
DEVICE_PRETTY_NAME="${DEVICE_PRETTY_NAME:-Orin nano 8GB}"
DEVICE_HOSTNAME="${DEVICE_HOSTNAME:-orin-nano-8gb}"
STATIC_IP="${STATIC_IP:-192.168.1.160}"
STATIC_PREFIX="${STATIC_PREFIX:-24}"
STATIC_GATEWAY="${STATIC_GATEWAY:-}"
STATIC_DNS="${STATIC_DNS:-}"
STATIC_IFACE="${STATIC_IFACE:-}"
LAN_CONNECTION_NAME="${LAN_CONNECTION_NAME:-ASV-Orin-LAN}"
FLASK_PORT="${FLASK_PORT:-5000}"
PYTHON_BIN="${PYTHON_BIN:-}"
STREAM_HIGH_RECORD="${STREAM_HIGH_RECORD:-0}"

log() {
  printf '[orin-defaults] %s\n' "$*"
}

fail() {
  printf '[orin-defaults] ERROR: %s\n' "$*" >&2
  exit 1
}

need_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    fail "run with sudo"
  fi
}

detect_lan_iface() {
  local iface
  for iface in /sys/class/net/*; do
    iface="$(basename "$iface")"
    case "$iface" in
      lo|wl*|wlan*|usb*|l4tbr*|docker*|br-*|can*) continue ;;
    esac
    [[ -r "/sys/class/net/$iface/type" ]] || continue
    [[ "$(cat "/sys/class/net/$iface/type")" == "1" ]] || continue
    printf '%s\n' "$iface"
    return 0
  done
  return 1
}

configure_hostname() {
  log "Setting hostname: $DEVICE_HOSTNAME ($DEVICE_PRETTY_NAME)"
  hostnamectl set-hostname "$DEVICE_HOSTNAME"
  hostnamectl set-hostname --pretty "$DEVICE_PRETTY_NAME"
  if grep -q '^127\.0\.1\.1' /etc/hosts; then
    sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$DEVICE_HOSTNAME/" /etc/hosts
  else
    printf '127.0.1.1\t%s\n' "$DEVICE_HOSTNAME" >> /etc/hosts
  fi
}

configure_static_lan() {
  command -v nmcli >/dev/null 2>&1 || fail "nmcli not found; NetworkManager is required"
  if [[ -z "$STATIC_IFACE" ]]; then
    STATIC_IFACE="$(detect_lan_iface || true)"
  fi
  [[ -n "$STATIC_IFACE" ]] || fail "no wired LAN interface found"

  log "Configuring $STATIC_IFACE as $STATIC_IP/$STATIC_PREFIX"
  if nmcli -t -f NAME connection show | grep -Fxq "$LAN_CONNECTION_NAME"; then
    nmcli connection modify "$LAN_CONNECTION_NAME" connection.interface-name "$STATIC_IFACE"
  else
    nmcli connection add type ethernet ifname "$STATIC_IFACE" con-name "$LAN_CONNECTION_NAME"
  fi

  nmcli connection modify "$LAN_CONNECTION_NAME" \
    connection.autoconnect yes \
    ipv4.method manual \
    ipv4.addresses "$STATIC_IP/$STATIC_PREFIX" \
    ipv6.method ignore

  if [[ -n "$STATIC_GATEWAY" ]]; then
    nmcli connection modify "$LAN_CONNECTION_NAME" ipv4.gateway "$STATIC_GATEWAY" ipv4.never-default no
  else
    nmcli connection modify "$LAN_CONNECTION_NAME" ipv4.gateway "" ipv4.never-default yes
  fi

  if [[ -n "$STATIC_DNS" ]]; then
    nmcli connection modify "$LAN_CONNECTION_NAME" ipv4.dns "$STATIC_DNS"
  else
    nmcli connection modify "$LAN_CONNECTION_NAME" ipv4.ignore-auto-dns yes
  fi

  nmcli connection up "$LAN_CONNECTION_NAME" || true
}

disable_usb_media_popups() {
  log "Disabling USB media popups for desktop sessions"
  if command -v gsettings >/dev/null 2>&1 && id "$RUN_USER" >/dev/null 2>&1; then
    sudo -u "$RUN_USER" dbus-run-session gsettings set org.gnome.desktop.media-handling automount false || true
    sudo -u "$RUN_USER" dbus-run-session gsettings set org.gnome.desktop.media-handling automount-open false || true
    sudo -u "$RUN_USER" dbus-run-session gsettings set org.gnome.desktop.media-handling autorun-never true || true
  fi

  if command -v dconf >/dev/null 2>&1; then
    mkdir -p /etc/dconf/db/local.d
    cat > /etc/dconf/db/local.d/00-asv-usb-media <<'EOF'
[org/gnome/desktop/media-handling]
automount=false
automount-open=false
autorun-never=true
EOF
    dconf update || true
  fi
}

install_backend_services() {
  log "Installing backend auto-start services"
  if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
      PYTHON_BIN="$REPO_DIR/.venv/bin/python"
    else
      PYTHON_BIN="/usr/bin/python3"
    fi
  fi
  REPO_DIR="$REPO_DIR" \
    RUN_USER="$RUN_USER" \
    FLASK_PORT="$FLASK_PORT" \
    PYTHON_BIN="$PYTHON_BIN" \
    STREAM_HIGH_RECORD="$STREAM_HIGH_RECORD" \
    bash "$REPO_DIR/scripts/install_systemd_services.sh"
}

need_root
configure_hostname
configure_static_lan
disable_usb_media_popups
install_backend_services

log "Done"
log "Backend: http://$STATIC_IP:$FLASK_PORT/api/runtime/status"
