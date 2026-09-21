#!/bin/bash
# Start the Missubibi backend and frontend from any checkout path.
# Use --sync-db after pulling when the local MySQL database may be stale.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_DB=0
if [ "${1:-}" = "--sync-db" ]; then
  SYNC_DB=1
elif [ "${1:-}" != "" ]; then
  echo "Usage: $0 [--sync-db]"
  exit 2
fi

if [ "$SYNC_DB" -eq 1 ]; then
  "$ROOT_DIR/database/ensure_current.sh" --sync
else
  "$ROOT_DIR/database/ensure_current.sh" --check
fi

cleanup() {
  if [ -n "${BACKEND_PID:-}" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "=== Starting Missubibi ==="
(cd "$ROOT_DIR/backend" && uv run uvicorn app.main:app --reload --port 8100) &
BACKEND_PID=$!

cd "$ROOT_DIR/frontend"
npm run dev
