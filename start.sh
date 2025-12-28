#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "🚀 Starting MCP Connector..."

# Ensure venv exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo "▶️  Running Connector..."
python3 connector.py
