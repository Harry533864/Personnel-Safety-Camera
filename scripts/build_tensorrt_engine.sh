#!/usr/bin/env bash
set -euo pipefail

ONNX_PATH="${1:-inference/models/yolo11n_person.onnx}"
ENGINE_PATH="${2:-inference/models/yolo11n_person.engine}"
TRTEXEC="${TRTEXEC:-/usr/src/tensorrt/bin/trtexec}"

if [[ ! -f "$ONNX_PATH" ]]; then
  echo "ONNX file not found: $ONNX_PATH" >&2
  exit 1
fi

if [[ ! -x "$TRTEXEC" ]]; then
  echo "trtexec not found or not executable: $TRTEXEC" >&2
  exit 1
fi

mkdir -p "$(dirname "$ENGINE_PATH")"

"$TRTEXEC" \
  --onnx="$ONNX_PATH" \
  --saveEngine="$ENGINE_PATH" \
  --fp16

echo "TensorRT engine output: $ENGINE_PATH"
