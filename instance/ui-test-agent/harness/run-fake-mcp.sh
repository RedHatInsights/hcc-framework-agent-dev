#!/bin/sh
set -eu

HARNESS_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$HARNESS_DIR/../../.." && pwd)
if [ "$#" -lt 1 ]; then
    echo "Usage: $0 jira|memory [additional fake_mcp_server.py arguments]" >&2
    exit 2
fi
KIND=$1
shift
case "$KIND" in
    jira|memory) ;;
    *) echo "Service must be jira or memory" >&2; exit 2 ;;
esac

exec uv run --project "$REPO_ROOT/dev-bot" --extra dev python "$HARNESS_DIR/fake_mcp_server.py" "$KIND" "$@"
