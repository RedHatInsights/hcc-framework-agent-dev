#!/bin/bash
set -eu

health_url="${UI_TEST_LOGIN_HELPER_HEALTH_URL:-http://127.0.0.1:8768/health}"
timeout="${UI_TEST_LOGIN_HELPER_HEALTH_TIMEOUT:-120}"

case "$timeout" in
    ''|*[!0-9]*)
        echo "FATAL: UI_TEST_LOGIN_HELPER_HEALTH_TIMEOUT must be an integer" >&2
        exit 64
        ;;
esac

elapsed=0
# The helper sidecar starts Chromium with the Stage-only proxy. Wait until its
# CDP endpoint is ready so the shared upstream browser preset sees that session
# and skips launching Chromium with the bot's general proxy settings.
while ! curl -fsS --noproxy '*' --max-time 3 "$health_url" >/dev/null 2>&1; do
    if [ "$elapsed" -ge "$timeout" ]; then
        echo "FATAL: UI-test browser helper not ready after ${timeout}s" >&2
        exit 1
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

exec /bin/bash /home/botuser/app/entrypoint.sh "$@"
