#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# talos-mcp-connector Test Script
# =============================================================================

echo "Testing talos-mcp-connector..."

echo "Running ruff check..."
ruff check . --exclude=.venv --exclude=tests 2>/dev/null || true

echo "Running ruff format check..."
ruff format --check . --exclude=.venv --exclude=tests 2>/dev/null || true

echo "Running pytest..."
pytest tests/ --maxfail=1 -q

echo "talos-mcp-connector tests passed."
