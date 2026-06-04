#!/usr/bin/env bash
set -euo pipefail

NVP_CONF="${NVP_CONF:-/etc/nvpmodel.conf}"
SUPER_CONFIG="${SUPER_CONFIG:-}"
TARGET_MODE_NAME="${TARGET_MODE_NAME:-MAXN_SUPER}"
HELPER_PATH="${HELPER_PATH:-/usr/local/sbin/asv-select-super-mode.sh}"
SERVICE_PATH="${SERVICE_PATH:-/etc/systemd/system/asv-super-mode.service}"
NVP_DROPIN_DIR="${NVP_DROPIN_DIR:-/etc/systemd/system/nvpmodel.service.d}"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Please run with sudo:"
  echo "  sudo $0"
  exit 1
fi

resolve_super_config() {
  if [[ -n "$SUPER_CONFIG" ]]; then
    [[ -f "$SUPER_CONFIG" ]] && echo "$SUPER_CONFIG"
    return
  fi

  compatible="$(tr '\0' '\n' </proc/device-tree/compatible 2>/dev/null || true)"
  case "$compatible" in
    *p3767-0003*|*p3767-0005*)
      [[ -f /etc/nvpmodel/nvpmodel_p3767_0003_super.conf ]] && echo /etc/nvpmodel/nvpmodel_p3767_0003_super.conf && return
      ;;
    *p3767-0004*)
      [[ -f /etc/nvpmodel/nvpmodel_p3767_0004_super.conf ]] && echo /etc/nvpmodel/nvpmodel_p3767_0004_super.conf && return
      ;;
    *p3767-0001*)
      [[ -f /etc/nvpmodel/nvpmodel_p3767_0001_super.conf ]] && echo /etc/nvpmodel/nvpmodel_p3767_0001_super.conf && return
      ;;
    *p3767-0000*|*p3767-0002*)
      [[ -f /etc/nvpmodel/nvpmodel_p3767_0000_super.conf ]] && echo /etc/nvpmodel/nvpmodel_p3767_0000_super.conf && return
      ;;
  esac

  current_target="$(readlink -f "$NVP_CONF" 2>/dev/null || true)"
  if [[ -n "$current_target" ]]; then
    if [[ "$current_target" == *_super.conf && -f "$current_target" ]]; then
      echo "$current_target"
      return
    fi
    derived="${current_target%.conf}_super.conf"
    if [[ -f "$derived" ]]; then
      echo "$derived"
      return
    fi
  fi

  find /etc/nvpmodel -maxdepth 1 -type f -name '*_super.conf' 2>/dev/null | sort | head -n 1
}

find_mode_id() {
  awk -v wanted="$TARGET_MODE_NAME" '
    /< POWER_MODEL/ {
      id = ""; name = "";
      if (match($0, /ID=[0-9]+/)) {
        id = substr($0, RSTART + 3, RLENGTH - 3)
      }
      if (match($0, /NAME=[^ >]+/)) {
        name = substr($0, RSTART + 5, RLENGTH - 5)
      }
      if (name == wanted) {
        print id;
        exit;
      }
    }
  ' "$1"
}

super_config="$(resolve_super_config)"
if [[ -z "$super_config" || ! -f "$super_config" ]]; then
  echo "No Super nvpmodel config found." >&2
  exit 2
fi

mode_id="$(find_mode_id "$super_config")"
if [[ -z "$mode_id" ]]; then
  echo "Target mode $TARGET_MODE_NAME not found in $super_config." >&2
  exit 3
fi

cat > "$HELPER_PATH" <<EOF
#!/usr/bin/env bash
set -euo pipefail

ln -sfn "$super_config" "$NVP_CONF"
rm -f /var/lib/nvpmodel/status

for dir in /sys/class/hwmon/*; do
  [[ -r "\$dir/name" ]] || continue
  [[ "\$(cat "\$dir/name")" == "ina3221" ]] || continue
  [[ -r "\$dir/in1_label" ]] || continue
  [[ "\$(cat "\$dir/in1_label")" == "VDD_IN" ]] || continue

  # Same VDD_IN limits NVIDIA applies for p3767-0003-super in nvpower.sh.
  [[ -w "\$dir/curr1_max" ]] && echo 5000 > "\$dir/curr1_max"
  [[ -w "\$dir/curr1_crit" ]] && echo 5000 > "\$dir/curr1_crit"
  [[ -w "\$dir/samples" ]] && echo 512 > "\$dir/samples"
done
EOF
chmod 0755 "$HELPER_PATH"

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=ASV select Jetson Super nvpmodel before NVIDIA nvpmodel service
After=nvpower.service
Requires=nvpower.service
Before=nvpmodel.service
ConditionPathExists=$super_config

[Service]
Type=oneshot
ExecStart=$HELPER_PATH
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

mkdir -p "$NVP_DROPIN_DIR"
cat > "$NVP_DROPIN_DIR/10-asv-super-mode.conf" <<EOF
[Unit]
Requires=
Requires=asv-super-mode.service
After=asv-super-mode.service

[Service]
ExecStartPost=/usr/sbin/nvpmodel -m $mode_id
EOF

systemctl daemon-reload
systemctl enable asv-super-mode.service
systemctl restart asv-super-mode.service
nvpmodel -m "$mode_id"

echo "Installed persistent Super mode service."
echo "  mode: $TARGET_MODE_NAME (id=$mode_id)"
echo "  config: $super_config"
