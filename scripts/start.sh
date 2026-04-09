#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SERVICE_NAME="talos-mcp-connector"
PID_FILE="/tmp/${SERVICE_NAME}.pid"
PORT="${TALOS_MCP_PORT:-8082}"
HOST="${TALOS_BIND_HOST:-127.0.0.1}"

source_env_file() {
    local file="$1"
    if [ -f "$file" ]; then
        set -a
        . "$file"
        set +a
    fi
}

source_env_file "$ROOT_DIR/.env"
source_env_file "$ROOT_DIR/.env.local"
source_env_file "$REPO_DIR/.env"
source_env_file "$REPO_DIR/.env.local"

cd "$REPO_DIR"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "$SERVICE_NAME is already running"
    exit 0
fi

echo "Starting $SERVICE_NAME on port $PORT..."
uvicorn main:app --port "$PORT" --host "$HOST" > "/tmp/${SERVICE_NAME}.log" 2>&1 &
echo $! > "$PID_FILE"
sleep 2

if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "✓ $SERVICE_NAME started (Port: $PORT)"
else
    echo "✗ $SERVICE_NAME failed to start"
    exit 1
fi
