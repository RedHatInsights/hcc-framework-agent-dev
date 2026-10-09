#!/bin/sh
set -eu

HARNESS_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$HARNESS_DIR/../../.." && pwd)

cd "$REPO_ROOT"
exec python3 -m unittest discover -s "$HARNESS_DIR/tests" -v
