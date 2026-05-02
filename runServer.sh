#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="/tmp/marlogspace-8011.pid"
LOG_FILE="/tmp/marlogspace-8011.log"
PORT="8011"

cd "$ROOT_DIR"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi

pkill -f "uvicorn app.main:app --host 127.0.0.1 --port ${PORT}" 2>/dev/null || true

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

nohup python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >"$LOG_FILE" 2>&1 &
NEW_PID="$!"
echo "$NEW_PID" >"$PID_FILE"

sleep 2

if kill -0 "$NEW_PID" 2>/dev/null; then
  echo "MarlogSpace started on http://127.0.0.1:${PORT}"
  echo "PID: $NEW_PID"
  echo "Log: $LOG_FILE"
else
  echo "Failed to start MarlogSpace. Check $LOG_FILE" >&2
  exit 1
fi
