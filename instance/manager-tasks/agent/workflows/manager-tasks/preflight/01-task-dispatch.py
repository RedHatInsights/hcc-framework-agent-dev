#!/usr/bin/env python3
"""Task dispatch — decides which task to run this cycle.

Checks each registered task's day schedule and readiness conditions.
Outputs the first actionable task, or skip if nothing to do.

Cycle frequency is handled by 00-cycle-sleep.py (separate concern).
"""

import json
import os
import subprocess
import sys
from datetime import date, timedelta


UPSTREAM_REPO = "RedHatInsights/weekly-status"
BRANCH_PATTERN = "hcc-team-weekly-report"
BOT_USERS = {
    os.environ.get("GH_USER_NAME", "platex-rehor-bot").lower(),
    "platex-rehor-bot",
}


def _friday_of_week(d=None):
    """Calculate the Friday of the current reporting week.

    The weekly-status repo organizes reports by Friday date (e.g.
    reports/2026/2026-07-25/). This function figures out which
    Friday the current day belongs to:
      - Mon–Sat → the upcoming (or current) Friday of that week
      - Sunday  → the previous Friday (that week is already done)

    Examples:
      Tuesday  2026-07-22 → Friday 2026-07-25
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


def _gh_json(args):
    """Run a GitHub CLI command and parse the JSON output.

    Wraps `gh <args>` in a subprocess with a 30s timeout.
    Returns the parsed JSON object, or None if the command fails,
    returns empty output, or produces invalid JSON. Errors are
    logged to stderr (visible in preflight logs, not in the prompt).
    """
    try:
        proc = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            print(f"gh command failed: {proc.stderr.strip()}", file=sys.stderr)
            return None
        output = proc.stdout.strip()
        if not output:
            return None
        return json.loads(output)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"gh command error: {exc}", file=sys.stderr)
        return None


def _find_weekly_pr(friday_str):
    """Search GitHub for an existing PR for this week's report.

    Looks for PRs in the upstream repo whose title and branch name
    contain the Friday date string (e.g. "hcc-team-weekly-report-2026-07-25").
    Searches all states (open, merged, closed) so we can detect
    already-merged PRs and skip the generate phase.

    Returns the PR dict (number, state, url, reviews, etc.) or None.
    """
    prs = _gh_json([
        "pr", "list",
        "--repo", UPSTREAM_REPO,
        "--state", "all",
        "--limit", "5",
        "--search", f"{BRANCH_PATTERN}-{friday_str} in:title",
        "--json", "number,state,title,headRefName,reviews,url",
    ])
    if not prs:
        return None

    for pr in prs:
        branch = pr.get("headRefName", "")
        if friday_str in branch and BRANCH_PATTERN in branch:
            return pr
    return None


def _has_changes_requested(pr):
    """Check if any reviewer has requested changes on the PR.

    A PR with CHANGES_REQUESTED reviews must not be auto-merged.
    The bot should address the feedback first.
    """
    reviews = pr.get("reviews", [])
    return any(r.get("state") == "CHANGES_REQUESTED" for r in reviews)


def _is_bot(login):
    """Check if a GitHub login belongs to our bot account.

    Used to distinguish bot comments/reviews from human ones when
    determining whether feedback has already been addressed.
    """
    return login.lower() in BOT_USERS


def _get_unaddressed_comments(pr):
    """Fetch PR comments that the bot hasn't addressed yet.

    Fetches all comments and reviews on the PR, then filters to only
    those from humans that arrived AFTER the bot's most recent reply.

    This is the key cost-saving check: if a reviewer left feedback at
    3pm and the bot replied at 3:15pm, the next preflight cycle sees
    no unaddressed comments and skips — no Claude session started,
    no tokens spent. Only genuinely new feedback triggers a session.

    Returns a list of unaddressed comment dicts, or empty list if
    everything has been handled.
    """
    number = pr.get("number")
    if not number:
        return []
    data = _gh_json([
        "pr", "view", str(number),
        "--repo", UPSTREAM_REPO,
        "--json", "comments,reviews",
    ])
    if not data:
        return []

    all_items = []
    for review in data.get("reviews", []):
        body = review.get("body", "").strip()
        if not body:
            continue
        author = review.get("author", {}).get("login", "unknown")
        all_items.append({
            "author": author,
            "state": review.get("state", ""),
            "body": body,
            "createdAt": review.get("submittedAt", review.get("createdAt", "")),
            "is_bot": _is_bot(author),
        })
    for comment in data.get("comments", []):
        body = comment.get("body", "").strip()
        if not body:
            continue
        author = comment.get("author", {}).get("login", "unknown")
        all_items.append({
            "author": author,
            "body": body,
            "createdAt": comment.get("createdAt", ""),
            "is_bot": _is_bot(author),
        })

    last_bot_action = max(
        (item["createdAt"] for item in all_items if item["is_bot"] and item["createdAt"]),
        default="",
    )

    unaddressed = [
        item for item in all_items
        if not item["is_bot"]
        and item.get("createdAt", "") > last_bot_action
    ]

    if not unaddressed and last_bot_action:
        print(
            f"All {len(all_items)} comments already addressed (bot last acted: {last_bot_action})",
            file=sys.stderr,
        )

    return unaddressed


def check_weekly_report():
    """Decide what weekly-report action to take this cycle.

    This is the main decision function for the weekly-report task.
    It checks the current day and PR state to determine which phase
    we're in:

    1. Tuesday, no PR exists     → generate reports, open PR
    2. PR open, new feedback     → address the review comments
    3. Wednesday, no blockers    → merge the PR
    4. PR already merged/closed  → nothing to do, skip

    Returns a tuple of (should_run, task_name, content):
      - should_run: True if a Claude session should start
      - task_name:  which task section the workflow should follow
      - content:    prompt data for the session (or skip reason)
    """
    today = date.today()
    weekday = today.weekday()  # Monday=0, Tuesday=1, Wednesday=2

    # TODO: Remove Monday (0) once testing is complete
    if weekday not in (0, 1, 2):  # Monday (testing), Tuesday, Wednesday
        return False, None, "Not Monday-Wednesday"

    friday = _friday_of_week(today)
    friday_str = friday.isoformat()

    pr = _find_weekly_pr(friday_str)

    task_id = f"weekly-report-{friday_str}"

    if pr is None:
        if weekday == 1:  # Tuesday, no PR — generate
            content = (
                f"## TASK: weekly-report-generate\n\n"
                f"Generate HCC weekly status reports for week ending {friday_str}.\n\n"
                f"- **Task ID**: {task_id}\n"
                f"- **Scope**: hcc-team all (all HCC sub-teams)\n"
                f"- **Repo**: {UPSTREAM_REPO}\n"
                f"- **Branch**: {{git_user}}/{BRANCH_PATTERN}-{friday_str}\n"
                f"- **Friday date**: {friday_str}\n"
            )
            return True, "weekly-report-generate", content
        return False, None, f"Wednesday but no PR found for {friday_str}"

    pr_state = pr.get("state", "").upper()
    pr_url = pr.get("url", "")
    pr_number = pr.get("number", "?")

    if pr_state == "MERGED":
        return False, None, f"PR #{pr_number} already merged"

    if pr_state == "CLOSED":
        return False, None, f"PR #{pr_number} was closed"

    # PR is open
    comments = _get_unaddressed_comments(pr)
    has_feedback = len(comments) > 0

    if has_feedback and _has_changes_requested(pr):
        feedback_text = "\n".join(
            f"- **{c['author']}** ({c.get('state', 'comment')}): {c['body'][:200]}"
            for c in comments
        )
        content = (
            f"## TASK: weekly-report-feedback\n\n"
            f"Address review feedback on PR #{pr_number}.\n\n"
            f"- **Task ID**: {task_id}\n"
            f"- **PR**: {pr_url}\n"
            f"- **Branch**: {pr.get('headRefName', '?')}\n"
            f"- **Friday date**: {friday_str}\n\n"
            f"### Review Comments\n\n{feedback_text}\n"
        )
        return True, "weekly-report-feedback", content

    if weekday == 2:  # Wednesday
        if _has_changes_requested(pr):
            feedback_text = "\n".join(
                f"- **{c['author']}** ({c.get('state', 'comment')}): {c['body'][:200]}"
                for c in comments
            )
            content = (
                f"## TASK: weekly-report-feedback\n\n"
                f"Address review feedback on PR #{pr_number} before merge.\n\n"
                f"- **Task ID**: {task_id}\n"
                f"- **PR**: {pr_url}\n"
                f"- **Branch**: {pr.get('headRefName', '?')}\n"
                f"- **Friday date**: {friday_str}\n\n"
                f"### Review Comments\n\n{feedback_text}\n"
            )
            return True, "weekly-report-feedback", content

        content = (
            f"## TASK: weekly-report-merge\n\n"
            f"Merge the weekly report PR — no blocking reviews.\n\n"
            f"- **Task ID**: {task_id}\n"
            f"- **PR**: {pr_url}\n"
            f"- **PR number**: {pr_number}\n"
            f"- **Friday date**: {friday_str}\n"
        )
        return True, "weekly-report-merge", content

    # Tuesday, PR exists, no changes requested — feedback cycle if there are comments
    if has_feedback:
        feedback_text = "\n".join(
            f"- **{c['author']}**: {c['body'][:200]}"
            for c in comments
        )
        content = (
            f"## TASK: weekly-report-feedback\n\n"
            f"Address review comments on PR #{pr_number}.\n\n"
            f"- **Task ID**: {task_id}\n"
            f"- **PR**: {pr_url}\n"
            f"- **Branch**: {pr.get('headRefName', '?')}\n"
            f"- **Friday date**: {friday_str}\n\n"
            f"### Review Comments\n\n{feedback_text}\n"
        )
        return True, "weekly-report-feedback", content

    return False, None, f"PR #{pr_number} open, no feedback yet"


# Task registry — add new tasks here
TASKS = [
    {
        "name": "weekly-report",
        "days": [0, 1, 2],  # Monday (testing), Tuesday, Wednesday  # TODO: Remove 0 once testing is complete
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
            json.dump(
                {"status": "start", "content": content},
                sys.stdout,
            )
            return

        print(f"Task {task['name']} skipped: {content}", file=sys.stderr)

    json.dump(
        {"status": "skip", "content": f"No tasks to run today ({today.strftime('%A')})"},
        sys.stdout,
    )


if __name__ == "__main__":
    main()
