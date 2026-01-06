#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="talos-mcp-connector"
PID_FILE="/tmp/${SERVICE_NAME}.pid"

cd "$REPO_DIR"

[ -f "$PID_FILE" ] && { kill "$(cat "$PID_FILE")" 2>/dev/null || true; rm -f "$PID_FILE"; }
rm -f "/tmp/${SERVICE_NAME}.log"
# Python artifacts
rm -rf *.egg-info build dist .venv venv .pytest_cache .ruff_cache __pycache__
# Coverage & reports
rm -f .coverage .coverage.* coverage.xml conformance.xml junit.xml 2>/dev/null || true
rm -rf htmlcov coverage 2>/dev/null || true
# Cache files
rm -rf .mypy_cache .pytype 2>/dev/null || true
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "✓ $SERVICE_NAME cleaned"
