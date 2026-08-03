#!/usr/bin/env python3
"""Cycle sleep — controls how long the runner waits between cycles.

Runs before the task dispatch script. Writes data/cycle-sleep.json
with a sleep duration based on the current Prague time slot. This
keeps frequency scheduling in deterministic Python — no AI tokens.

KEDA provides broad pod on/off windows (e.g. Tue 9am-11pm).
This script provides fine-grained pacing within those windows.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
CYCLE_SLEEP_FILE = SCRIPT_DIR / "data" / "cycle-sleep.json"

# Sleep duration by time slot (all times UTC).
#
# Tuesday:
#   7am–11am  → 2h     (PR just opened, few reviewers yet)
#   11am–1pm  → 1h     (quiet period, hourly check)
#   1pm–4pm   → 20min  (peak review time)
#   4pm–9pm   → 2h     (US East coast catching up, low volume)
#
# Wednesday:
#   7am–11am  → 2h     (morning, light feedback)
#   11am–2pm  → 20min  (final push before merge)
#   2pm+      → 24h    (merge done, wait for KEDA to scale down)
SCHEDULE = {
    # TODO: Remove Monday and Friday once testing is complete
    0: [  # Monday (testing only)
        (7, 21, 1200),
    ],
    4: [  # Friday (testing only)
        (7, 21, 1200),
    ],
    1: [  # Tuesday
        (7, 11, 7200),
        (11, 13, 3600),
        (13, 16, 1200),
        (16, 21, 7200),
    ],
    2: [  # Wednesday
        (7, 11, 7200),
        (11, 14, 1200),
        (14, 21, 86400),
    ],
}


def _now_utc():
    """Get the current time in UTC.

    All schedule slots are defined in UTC, so every time
    comparison in this script uses this function as the single
    source of "what time is it now."
    """
    return datetime.now(timezone.utc)


def _get_recommended_sleep():
    """Look up the current Prague time in the SCHEDULE table and return
    how long the runner should sleep before the next cycle.

    Walks through the time slots for today's weekday. If the current
    hour falls within a slot, returns that slot's sleep duration.
    If today isn't in the schedule at all (e.g. Thursday when only
    Tue/Wed are defined), returns a 1h default.

    Returns (sleep_seconds, reason_string).
    """
    now = _now_utc()
    weekday = now.weekday()
    hour = now.hour

    slots = SCHEDULE.get(weekday)
    if not slots:
        return 3600, "outside scheduled days"

    for start_h, end_h, sleep_val in slots:
        if start_h <= hour < end_h:
            if sleep_val == "skip":
                secs = (end_h - hour) * 3600 - now.minute * 60
                return max(
                    secs, 600
                ), f"gap {start_h}:00-{end_h}:00, sleeping until next window UTC"
            return sleep_val, f"slot {start_h}:00-{end_h}:00 UTC"

    return 3600, "outside defined time slots"


def main():
    """Write the cycle-sleep file and exit with skip status.

    This script always outputs "skip" — it never starts a Claude
    session. Its only job is to write data/cycle-sleep.json so the
    runner knows how long to wait before the next cycle. The actual
    task dispatch happens in 01-task-dispatch.py (runs after this).
    """
    sleep_secs, reason = _get_recommended_sleep()

    CYCLE_SLEEP_FILE.parent.mkdir(parents=True, exist_ok=True)
    CYCLE_SLEEP_FILE.write_text(
        json.dumps(
            {
                "recommended_sleep": sleep_secs,
                "reason": reason,
            }
        )
    )

    print(f"Cycle sleep: {sleep_secs}s ({reason})", file=sys.stderr)
    json.dump(
        {"status": "skip", "content": f"Cycle sleep set: {sleep_secs}s ({reason})"},
        sys.stdout,
    )


if __name__ == "__main__":
    main()
