#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ONNX_PATH="${1:-$REPO_DIR/inference/models/yolo11n_person.onnx}"
CALIB_CACHE="${CALIB_CACHE:-$REPO_DIR/inference/calibration/baumer_yolo11n_person_int8.cache}"
MODEL_ROOT="${MODEL_ROOT:-$REPO_DIR/inference/models}"
MODEL_NAME="${MODEL_NAME:-Asva_person_v0518_int8}"
ENGINE_DIR="$MODEL_ROOT/$MODEL_NAME"
ENGINE_PATH="${ENGINE_PATH:-$ENGINE_DIR/$MODEL_NAME.engine}"
CLASS_TXT="${CLASS_TXT:-}"
TRTEXEC="${TRTEXEC:-}"

find_trtexec() {
  if [[ -n "$TRTEXEC" && -x "$TRTEXEC" ]]; then
    echo "$TRTEXEC"
    return
  fi
  for candidate in /usr/src/tensorrt/bin/trtexec /usr/bin/trtexec "$(command -v trtexec 2>/dev/null || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      echo "$candidate"
      return
    fi
  done
}

TRTEXEC_BIN="$(find_trtexec || true)"
if [[ -z "$TRTEXEC_BIN" ]]; then
  cat >&2 <<'EOF'
trtexec was not found.

Install/enable TensorRT samples or set TRTEXEC=/path/to/trtexec on the Baumer camera.
The INT8 engine must be generated on the final camera hardware.
EOF
  exit 1
fi

if [[ ! -f "$ONNX_PATH" ]]; then
  echo "ONNX file not found: $ONNX_PATH" >&2
  exit 1
fi

if [[ ! -f "$CALIB_CACHE" ]]; then
  cat >&2 <<EOF
INT8 calibration cache not found: $CALIB_CACHE

Do not build a production INT8 safety model without representative calibration.
Prepare a calibration cache from real camera scenes first, then rerun:
  CALIB_CACHE=/path/to/cache $0
EOF
  exit 2
fi

mkdir -p "$ENGINE_DIR"

"$TRTEXEC_BIN" \
  --onnx="$ONNX_PATH" \
  --saveEngine="$ENGINE_PATH" \
  --int8 \
  --calib="$CALIB_CACHE"

if [[ -n "$CLASS_TXT" && -f "$CLASS_TXT" ]]; then
  cp "$CLASS_TXT" "$ENGINE_DIR/$MODEL_NAME.txt"
elif [[ ! -f "$ENGINE_DIR/$MODEL_NAME.txt" ]]; then
  printf "person\n" > "$ENGINE_DIR/$MODEL_NAME.txt"
fi

echo "INT8 TensorRT engine: $ENGINE_PATH"
echo "Model name for AIConfig.yaml: $MODEL_NAME"
