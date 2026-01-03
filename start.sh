#!/usr/bin/env bash
set -euo pipefail
echo "DEPRECATED: Use ./scripts/start.sh (this wrapper will be removed in a future release)." >&2
exec "$(cd "$(dirname "$0")" && pwd)/scripts/start.sh" "$@"
