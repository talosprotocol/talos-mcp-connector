#!/usr/bin/env bash
set -e

# Run pytest with coverage
PYTHONPATH=src pytest tests/
