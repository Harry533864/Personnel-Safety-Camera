#!/usr/bin/env bash
set -euo pipefail

REQUIRE_SUPER_MODE="${REQUIRE_SUPER_MODE:-1}"
REQUIRE_HW_ENCODER="${REQUIRE_HW_ENCODER:-1}"
REQUIRE_CAMERA_1080P60="${REQUIRE_CAMERA_1080P60:-1}"
REQUIRE_BACKEND="${REQUIRE_BACKEND:-0}"
CAMERA_DEVICE="${CAMERA_DEVICE:-/dev/video0}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:5000/api/runtime/status}"

failures=0

fail() {
  echo "[FAIL] $*" >&2
  failures=$((failures + 1))
}

pass() {
  echo "[ OK ] $*"
}

check_super_mode() {
  if ! command -v nvpmodel >/dev/null 2>&1; then
    fail "nvpmodel not found"
    return
  fi

  current="$(nvpmodel -q 2>/dev/null | awk -F': ' '/NV Power Mode/ {print $2; exit}')"
  available="$(awk '/< POWER_MODEL/ {print}' /etc/nvpmodel.conf 2>/dev/null || true)"

  if echo "$current" | grep -Eq 'MAXN_SUPER|SUPER|25W|MAXN'; then
    pass "Super-capable power mode active: $current"
    return
  fi

  if [[ "$REQUIRE_SUPER_MODE" == "1" ]]; then
    fail "Super/25W mode not active. Current=${current:-unknown}. Available modes: ${available//$'\n'/; }"
  else
    echo "[WARN] Super/25W mode not active. Current=${current:-unknown}"
  fi
}

check_hw_encoder() {
  model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"
  if ! ls /dev/nvhost-* 2>/dev/null | grep -Eq 'nvenc|msenc'; then
    if [[ "$REQUIRE_HW_ENCODER" == "1" ]]; then
      fail "Hardware video encoder device is not present${model:+ on $model}. Use a Jetson module with NVENC, or ship with the software x264 path instead."
    else
      echo "[WARN] Hardware video encoder device is not present${model:+ on $model}; software x264 path required."
    fi
    return
  fi

  missing=()
  for element in nvv4l2h264enc nvvidconv; do
    if ! gst-inspect-1.0 "$element" >/dev/null 2>&1; then
      missing+=("$element")
    fi
  done

  if [[ "${#missing[@]}" -eq 0 ]]; then
    pass "Jetson hardware H264 encoder path available"
  elif [[ "$REQUIRE_HW_ENCODER" == "1" ]]; then
    fail "Missing GStreamer hardware encoder elements: ${missing[*]}. Do not ship 1080p60 units until fixed."
  else
    echo "[WARN] Missing GStreamer hardware encoder elements: ${missing[*]}"
  fi
}

check_camera() {
  if [[ ! -e "$CAMERA_DEVICE" ]]; then
    fail "Camera device not found: $CAMERA_DEVICE"
    return
  fi

  if ! command -v v4l2-ctl >/dev/null 2>&1; then
    fail "v4l2-ctl not found"
    return
  fi

  formats="$(v4l2-ctl -d "$CAMERA_DEVICE" --list-formats-ext 2>/dev/null || true)"
  if echo "$formats" | grep -A8 '1920x1080' | grep -q '60.000 fps'; then
    pass "$CAMERA_DEVICE supports 1920x1080@60"
  elif [[ "$REQUIRE_CAMERA_1080P60" == "1" ]]; then
    fail "$CAMERA_DEVICE does not report 1920x1080@60 support"
  else
    echo "[WARN] $CAMERA_DEVICE does not report 1920x1080@60 support"
  fi
}

check_backend() {
  if [[ "$REQUIRE_BACKEND" != "1" ]]; then
    return
  fi

  if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 3 "$BACKEND_URL" >/dev/null; then
    pass "Backend responds: $BACKEND_URL"
  else
    fail "Backend does not respond: $BACKEND_URL"
  fi
}

check_super_mode
check_hw_encoder
check_camera
check_backend

if [[ "$failures" -gt 0 ]]; then
  echo
  echo "Factory readiness: FAILED ($failures issue(s))."
  exit 1
fi

echo
echo "Factory readiness: PASSED."
