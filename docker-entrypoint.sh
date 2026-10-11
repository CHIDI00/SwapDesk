#!/usr/bin/env bash
# Run the web API and the queue worker in one container so both share the
# same SQLite database (SWAPDESK_DB) on the mounted disk. A Render persistent
# disk attaches to a single service, so the API and worker cannot be split
# into two services without splitting their shared state.
set -euo pipefail

python -m swapdesk.worker &
WORKER_PID=$!

uvicorn swapdesk.api:app --host 0.0.0.0 --port "${PORT:-8000}" &
WEB_PID=$!

# If either process exits, tear down the other so the container restarts
# cleanly instead of lingering half-alive.
trap 'kill "$WORKER_PID" "$WEB_PID" 2>/dev/null || true' TERM INT
wait -n "$WORKER_PID" "$WEB_PID"
