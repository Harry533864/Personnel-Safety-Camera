#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

cd "$REPO_DIR"

if [[ ! -d node_modules ]]; then
  npm install
fi

echo "Starting frontend on http://192.168.18.172:${FRONTEND_PORT}"
exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
