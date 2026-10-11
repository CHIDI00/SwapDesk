#!/usr/bin/env bash
# Run the web API and the queue worker in one container so both share the
# same SQLite database (SWAPDESK_DB) on the mounted disk. A Render persistent
# disk attaches to a single service, so the API and worker cannot be split
# into two services without splitting their shared state. Agent checkpoints
# live next to the database (<db>.agent-checkpoints.sqlite), so they share
# the same disk automatically.
#
# Supervision contract (one worker/service for this SQLite deployment):
# - Either child exiting terminates and reaps the other; the container
#   exit status is the first failing child's status (0 when both are
#   stopped via signal).
# - TERM/INT reaches both children; cleanup escalates to KILL after a
#   bounded 10s grace so shutdown never hangs forever.
# - SWAPDESK_WORKER_CMD / SWAPDESK_API_CMD override the child commands
#   (used by supervision tests with fake children; unset in production).
set -euo pipefail

if [ -n "${SWAPDESK_WORKER_CMD:-}" ]; then
    # Unquoted on purpose: env override holds a plain test command.
    # shellcheck disable=SC2086
    bash -c "$SWAPDESK_WORKER_CMD" &
else
    python -m swapdesk.worker &
fi
WORKER_PID=$!

if [ -n "${SWAPDESK_API_CMD:-}" ]; then
    # shellcheck disable=SC2086
    bash -c "$SWAPDESK_API_CMD" &
else
    uvicorn swapdesk.api:app --host 0.0.0.0 --port "${PORT:-8000}" &
fi
WEB_PID=$!

cleanup() {
    kill "$WORKER_PID" "$WEB_PID" 2>/dev/null || true
    for _ in $(seq 1 10); do
        kill -0 "$WORKER_PID" "$WEB_PID" 2>/dev/null || break
        sleep 1
    done
    kill -9 "$WORKER_PID" "$WEB_PID" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup TERM INT EXIT

set +e
wait -n "$WORKER_PID" "$WEB_PID"
STATUS=$?
set -e
cleanup
trap - TERM INT EXIT
exit "$STATUS"
