#!/usr/bin/env bash
set -euo pipefail

APPLY_JETSON_CLOCKS="${APPLY_JETSON_CLOCKS:-0}"
DRY_RUN="${DRY_RUN:-0}"
NVP_CONF="${NVP_CONF:-/etc/nvpmodel.conf}"
SUPER_CONFIG="${SUPER_CONFIG:-}"
BACKUP_LINK_RECORD="${BACKUP_LINK_RECORD:-/etc/nvpmodel.conf.asv-backup-target}"

if ! command -v nvpmodel >/dev/null 2>&1; then
  echo "nvpmodel not found. This board cannot pass Super mode validation." >&2
  exit 2
fi

find_super_mode() {
  awk '
    /< POWER_MODEL/ {
      id = ""; name = "";
      if (match($0, /ID=[0-9]+/)) {
        id = substr($0, RSTART + 3, RLENGTH - 3)
      }
      if (match($0, /NAME=[^ >]+/)) {
        name = substr($0, RSTART + 5, RLENGTH - 5)
      }
      if (name ~ /MAXN_SUPER/) {
        maxn_super = id " " name
      } else if (name ~ /SUPER/) {
        super = id " " name
      } else if (name ~ /25W/) {
        mode25w = id " " name
      } else if (name ~ /MAXN/) {
        maxn = id " " name
      }
    }
    END {
      if (maxn_super != "") print maxn_super;
      else if (super != "") print super;
      else if (mode25w != "") print mode25w;
      else if (maxn != "") print maxn;
    }
  ' "$NVP_CONF" | head -n 1
}

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

config_has_super_mode() {
  grep -Eq '< POWER_MODEL .*NAME=(MAXN_SUPER|SUPER|25W|MAXN)' "$1"
}

current_mode="$(nvpmodel -q 2>/dev/null | awk -F': ' '/NV Power Mode/ {print $2; exit}')"
candidate="$(find_super_mode || true)"

if [[ -z "$candidate" ]]; then
  super_config="$(resolve_super_config)"
  if [[ -z "$super_config" || ! -f "$super_config" ]] || ! config_has_super_mode "$super_config"; then
    echo "No 25W/MAXN_SUPER power mode found in $NVP_CONF or /etc/nvpmodel/*_super.conf." >&2
    echo "Current mode: ${current_mode:-unknown}" >&2
    echo "This usually means the board is not flashed with a Super-capable JetPack/BSP." >&2
    echo "Do not mark this unit as 67 TOPS ready." >&2
    exit 3
  fi

  echo "Current nvpmodel config has no Super mode: $(readlink -f "$NVP_CONF" 2>/dev/null || echo "$NVP_CONF")"
  echo "Found Super config: $super_config"

  if [[ "$DRY_RUN" == "1" ]]; then
    NVP_CONF="$super_config"
    candidate="$(find_super_mode || true)"
  else
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
      echo "Please run with sudo to switch nvpmodel config and apply power mode:"
      echo "  sudo $0"
      exit 1
    fi

    if [[ -L "$NVP_CONF" ]]; then
      readlink "$NVP_CONF" > "$BACKUP_LINK_RECORD"
    elif [[ -e "$NVP_CONF" ]]; then
      cp -a "$NVP_CONF" "$NVP_CONF.asv-backup"
    fi

    ln -sfn "$super_config" "$NVP_CONF"
    candidate="$(find_super_mode || true)"
  fi
fi

mode_id="${candidate%% *}"
mode_name="${candidate#* }"

echo "Current power mode: ${current_mode:-unknown}"
echo "Target power mode: $mode_name (id=$mode_id)"
echo "Target nvpmodel config: $(readlink -f "$NVP_CONF" 2>/dev/null || echo "$NVP_CONF")"

if [[ "$DRY_RUN" == "1" ]]; then
  exit 0
fi

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Please run with sudo to apply power mode:"
  echo "  sudo $0"
  exit 1
fi

nvpmodel -m "$mode_id"

if [[ "$APPLY_JETSON_CLOCKS" == "1" ]]; then
  if command -v jetson_clocks >/dev/null 2>&1; then
    jetson_clocks
  else
    echo "jetson_clocks not found; skipped."
  fi
fi

nvpmodel -q
