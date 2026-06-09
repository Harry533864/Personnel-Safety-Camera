#!/usr/bin/env bash
set -euo pipefail

RUN_USER="${RUN_USER:-baumer}"
HOME_DIR="${CAM_HOME_DIR:-/home/$RUN_USER}"
PROJECT_DIR="${CAM_PROJECT_ROOT:-$HOME_DIR/Cam_flaskvue}"
LOG_DIR="${CAM_LOG_DIR:-$PROJECT_DIR/logs}"
MIN_FREE_MB="${CAM_HOME_MIN_FREE_MB:-120}"
CRITICAL_FREE_MB="${CAM_HOME_CRITICAL_FREE_MB:-60}"
MAX_LOG_BYTES="${CAM_LOG_MAX_BYTES:-1048576}"
LOG_BACKUPS="${CAM_LOG_BACKUP_COUNT:-2}"
VIDEO_RETENTION_DAYS="${CAM_VIDEO_RETENTION_DAYS:-7}"

free_mb() {
  df -Pm "$HOME_DIR" | awk 'NR == 2 { print $4 }'
}

rotate_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0

  local size
  size="$(stat -c '%s' "$file" 2>/dev/null || echo 0)"
  [[ "$size" -gt "$MAX_LOG_BYTES" ]] || return 0

  local i
  for ((i = LOG_BACKUPS; i >= 1; i--)); do
    if [[ "$i" -eq "$LOG_BACKUPS" ]]; then
      rm -f "$file.$i"
    elif [[ -f "$file.$i" ]]; then
      mv -f "$file.$i" "$file.$((i + 1))"
    fi
  done

  cp -f "$file" "$file.1"
  : > "$file"
}

rotate_logs() {
  mkdir -p "$LOG_DIR"
  local file
  for file in "$LOG_DIR"/*.log "$LOG_DIR"/*.out.log "$LOG_DIR"/*.err.log; do
    [[ -e "$file" ]] || continue
    rotate_file "$file"
  done
}

cleanup_runtime_junk() {
  find "$LOG_DIR" -maxdepth 1 -type f \( -name '*.tmp' -o -name '*.old' \) -delete 2>/dev/null || true
  find "$PROJECT_DIR/inference/configs/runtime" -maxdepth 1 -type f -name '*.tmp' -delete 2>/dev/null || true
  find "$PROJECT_DIR" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
  find "$PROJECT_DIR" -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
}

cleanup_deploy_leftovers() {
  find "$HOME_DIR" -maxdepth 1 -type f \
    \( -name 'baumer_backend_*.tar.gz' -o -name 'baumer_wheelhouse_*.tar.gz' \) \
    -delete 2>/dev/null || true
}

cleanup_browser_cache() {
  rm -rf "$HOME_DIR/.cache/mozilla/firefox" 2>/dev/null || true
  rm -rf "$HOME_DIR/.mozilla/firefox"/*/saved-telemetry-pings 2>/dev/null || true
  rm -rf "$HOME_DIR/.mozilla/firefox"/*/datareporting/archived 2>/dev/null || true
}

cleanup_old_video() {
  local video_dir="$HOME_DIR/video"
  [[ -d "$video_dir" ]] || return 0
  find "$video_dir" -type f \( -name '*.mkv' -o -name '*.mp4' -o -name '*.avi' \) \
    -mtime "+$VIDEO_RETENTION_DAYS" -delete 2>/dev/null || true
  find "$video_dir" -type f -name '*.json' -mtime "+$VIDEO_RETENTION_DAYS" -delete 2>/dev/null || true
}

cleanup_critical_cache() {
  rm -rf "$HOME_DIR/wheelhouse_py38_aarch64" 2>/dev/null || true
  cleanup_browser_cache
}

main() {
  if [[ ! -d "$HOME_DIR" ]]; then
    echo "Storage guard skipped; home directory not found: $HOME_DIR" >&2
    exit 0
  fi

  rotate_logs
  cleanup_runtime_junk
  cleanup_deploy_leftovers
  cleanup_old_video

  local free
  free="$(free_mb)"
  if [[ "$free" -lt "$MIN_FREE_MB" ]]; then
    cleanup_browser_cache
    free="$(free_mb)"
  fi

  if [[ "$free" -lt "$CRITICAL_FREE_MB" ]]; then
    cleanup_critical_cache
    free="$(free_mb)"
  fi

  echo "Storage guard: /home free ${free}MB"
  exit 0
}

main "$@"
