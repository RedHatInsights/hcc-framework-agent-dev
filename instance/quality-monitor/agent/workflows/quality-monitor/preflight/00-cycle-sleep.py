#!/usr/bin/env python3
"""Cycle sleep -- sets a 24-hour pause between quality-monitor cycles.

KEDA provides broad pod on/off windows (e.g. weekdays 9am-11pm).
This script tells the runner to sleep 24 hours after each cycle,
ensuring the quality scan runs at most once per KEDA window.
"""

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
CYCLE_SLEEP_FILE = SCRIPT_DIR / "data" / "cycle-sleep.json"

SLEEP_SECONDS = 86400  # 24 hours


def main():
    CYCLE_SLEEP_FILE.parent.mkdir(parents=True, exist_ok=True)
    CYCLE_SLEEP_FILE.write_text(
        json.dumps(
            {"recommended_sleep": SLEEP_SECONDS, "reason": "daily scan complete"}
        )
    )

    print(f"Cycle sleep: {SLEEP_SECONDS}s (daily scan complete)", file=sys.stderr)
    json.dump(
        {"status": "skip", "content": f"Cycle sleep set: {SLEEP_SECONDS}s"},
        sys.stdout,
    )


if __name__ == "__main__":
    main()
