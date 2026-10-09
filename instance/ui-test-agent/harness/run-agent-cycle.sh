#!/bin/sh
set -eu

HARNESS_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

exec python3 "$HARNESS_DIR/run_agent_cycle.py" "$@"
