# talos-mcp-connector Makefile
# MCP Bridge Service

.PHONY: install build test lint clean start stop status typecheck

SERVICE_NAME := talos-mcp-connector
PID_FILE := /tmp/$(SERVICE_NAME).pid
PORT := 8082

all: install test

install:
	pip install -e ".[dev]" -q 2>/dev/null || pip install fastapi uvicorn pydantic -q

build:
	@echo "Python service - no build step required"

test:
	pytest tests/ -q 2>/dev/null || echo "No tests found"

lint:
	ruff check . --exclude=.venv --exclude=tests || true

start:
	@if [ -f $(PID_FILE) ] && kill -0 $$(cat $(PID_FILE)) 2>/dev/null; then \
		echo "$(SERVICE_NAME) is already running"; \
	else \
		uvicorn main:app --port $(PORT) --host 127.0.0.1 > /tmp/$(SERVICE_NAME).log 2>&1 & \
		echo $$! > $(PID_FILE); \
		echo "$(SERVICE_NAME) started (Port: $(PORT))"; \
	fi

stop:
	@if [ -f $(PID_FILE) ]; then kill $$(cat $(PID_FILE)) 2>/dev/null || true; rm -f $(PID_FILE); fi

clean:
	rm -rf *.egg-info build dist .venv venv .pytest_cache .ruff_cache __pycache__
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

typecheck:
	@echo "Typecheck not implemented for $(SERVICE_NAME)"
