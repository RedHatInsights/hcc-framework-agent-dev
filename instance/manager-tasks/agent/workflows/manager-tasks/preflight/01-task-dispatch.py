#!/usr/bin/env python3
"""Task dispatch — decides which task to run this cycle.

Checks each registered task's day schedule and readiness conditions.
Outputs the first actionable task, or skip if nothing to do.

Uses the bot framework's shared utilities (get_tasks, get_task_prs,
upstream_repo) and the built-in gh_pr_status module for PR checks.
Task state (last_addressed, status, PR info) comes from the memory
server — no custom GitHub queries needed.

Cycle frequency is handled by 00-cycle-sleep.py (separate concern).
"""

import sys
from datetime import date, datetime, timedelta, timezone

from common import get_tasks, output_result
from gh_pr_status import has_new_feedback, enrich_gh


MERGE_HOUR_UTC = 10  # 10am UTC = 12pm Prague (CEST)


UPSTREAM_REPO = "RedHatInsights/weekly-status"
BRANCH_PATTERN = "hcc-team-weekly-report"


def _is_merge_time():
    """Check if current UTC time is at or past the merge hour (11am UTC / 1pm Prague)."""
    now_utc = datetime.now(timezone.utc)
    return now_utc.hour >= MERGE_HOUR_UTC


def _friday_of_week(d=None):
    """Calculate the Friday of the current reporting week.

    The weekly-status repo organizes reports by Friday date (e.g.
    reports/2026/2026-07-25/). This function figures out which
    Friday the current day belongs to:
      - Mon–Sat → the upcoming (or current) Friday of that week
      - Sunday  → the previous Friday (that week is already done)

    Examples:
      Monday   2026-07-21 → Friday 2026-07-25
      Friday   2026-07-25 → Friday 2026-07-25
      Sunday   2026-07-27 → Friday 2026-07-25
    """
    if d is None:
        d = date.today()
    weekday = d.weekday()  # Monday=0 ... Sunday=6
    if weekday == 6:  # Sunday
        return d - timedelta(days=2)
    days_until_friday = 4 - weekday
    return d + timedelta(days=days_until_friday)


def _find_task_for_week(tasks, friday_str):
    """Find an existing memory-server task for this week's report.

    Looks for a task with external_key matching the weekly-report
    task ID pattern (e.g. "weekly-report-2026-07-25"). Returns
    the task dict or None.
    """
    task_id = f"weekly-report-{friday_str}"
    for t in tasks:
        if t.get("external_key") == task_id:
            return t
    return None


def check_weekly_report():
    """Decide what weekly-report action to take this cycle.

    This is the main decision function for the weekly-report task.
    It uses the memory server's task state and the built-in
    gh_pr_status module to determine which phase we're in:

    1. No task exists yet (Monday)        → generate reports, open PR
    2. Task has PR with new feedback      → address the review comments
    3. Tuesday 1pm Prague, no blockers    → merge the PR
    4. PR already merged / task done      → nothing to do, skip

    Returns a tuple of (should_run, task_name, content):
      - should_run: True if a Claude session should start
      - task_name:  which task section the workflow should follow
      - content:    prompt data for the session (or skip reason)
    """
    today = date.today()
    weekday = today.weekday()  # Monday=0, Tuesday=1

    if weekday not in (0, 1):  # Monday (generate), Tuesday (feedback/merge)
        return False, None, "Not a scheduled day"

    friday = _friday_of_week(today)
    friday_str = friday.isoformat()
    task_id = f"weekly-report-{friday_str}"

    tasks = get_tasks()
    task = _find_task_for_week(tasks, friday_str)

    # No task exists yet — generate phase (Monday)
    if task is None:
        if weekday == 0:
            content = (
                f"## TASK: weekly-report-generate\n\n"
                f"Generate HCC weekly status reports for week ending {friday_str}.\n\n"
                f"- **Task ID**: {task_id}\n"
                f"- **Task status**: new\n"
                f"- **Scope**: hcc-team all (all HCC sub-teams)\n"
                f"- **Repo**: {UPSTREAM_REPO}\n"
                f"- **Branch**: {{git_user}}/{BRANCH_PATTERN}-{friday_str}\n"
                f"- **Friday date**: {friday_str}\n"
            )
            return True, "weekly-report-generate", content
        return False, None, f"Tuesday but no task found for {friday_str}"

    # Task exists — check its status
    status = task.get("status", "")

    if status == "done":
        return False, None, f"Task {task_id} already done"

    # Check if the task has PRs and enrich with GH data
    enriched = enrich_gh(task)

    if enriched:
        pr_issues = enriched["issues"]

        # PR was merged — task should be marked done
        if "merged" in pr_issues:
            return False, None, f"PR already merged for {task_id}"

        # PR was closed
        if "closed" in pr_issues:
            return False, None, f"PR closed for {task_id}"

        # PR has new feedback to address
        if has_new_feedback(enriched):
            from common import fmt_comments, fmt_task_header

            lines = fmt_task_header(task)
            for p in enriched["prs"]:
                issue_str = ",".join(p["issues"]) if p["issues"] else "clean"
                lines.append(f"  PR {p['repo']}#{p['num']} [{issue_str}]")
            if enriched["pr_comments"]:
                lines.append(
                    fmt_comments(
                        enriched["pr_comments"],
                        "review_comments",
                        since=task.get("last_addressed"),
                    )
                )

            content = (
                f"## TASK: weekly-report-feedback\n\n"
                f"Address review feedback on the weekly report PR.\n\n"
                f"- **Task ID**: {task_id}\n"
                f"- **Task status**: in_progress\n"
                f"- **Friday date**: {friday_str}\n\n"
                f"### PR Details\n\n" + "\n".join(lines) + "\n"
            )
            return True, "weekly-report-feedback", content

        # Tuesday after 1pm Prague, no blocking reviews — merge
        if weekday == 1 and _is_merge_time():
            pr_info = enriched["prs"][0] if enriched["prs"] else {}
            content = (
                f"## TASK: weekly-report-merge\n\n"
                f"Merge the weekly report PR — no blocking reviews.\n\n"
                f"- **Task ID**: {task_id}\n"
                f"- **Task status**: in_progress\n"
                f"- **PR**: {pr_info.get('repo', UPSTREAM_REPO)}#{pr_info.get('num', '?')}\n"
                f"- **Friday date**: {friday_str}\n"
            )
            return True, "weekly-report-merge", content

    return False, None, f"Task {task_id} [{status}], no action needed"


# Task registry — add new tasks here
TASKS = [
    {
        "name": "weekly-report",
        "days": [0, 1],  # Monday (generate), Tuesday (feedback/merge)
        "check": check_weekly_report,
    },
    # Future tasks:
    # {"name": "jira-cleanup", "days": [3], "check": check_jira_cleanup},
]


def main():
    """Entry point — iterate the task registry and dispatch the first match.

    Walks through TASKS in order. For each task scheduled for today,
    calls its check function. The first one that returns should_run=True
    gets dispatched (its content becomes the Claude session prompt).
    If nothing matches, outputs skip — no session starts.
    """
    today = date.today()
    weekday = today.weekday()

    for task in TASKS:
        if weekday not in task["days"]:
            continue

        should_run, task_name, content = task["check"]()

        if should_run:
            print(f"Dispatching task: {task_name}", file=sys.stderr)
            output_result("start", content)
            return

        print(f"Task {task['name']} skipped: {content}", file=sys.stderr)

    output_result("skip", f"No tasks to run today ({today.strftime('%A')})")


if __name__ == "__main__":
    main()
