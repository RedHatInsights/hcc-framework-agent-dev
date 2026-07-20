#!/usr/bin/env python3
"""Manager tasks preflight — dispatch tasks based on day of week.

Checks each registered task's schedule and readiness conditions.
Outputs the first actionable task, or skip if nothing to do.
"""

import json
import subprocess
import sys
from datetime import date, timedelta


UPSTREAM_REPO = "RedHatInsights/weekly-status"
BRANCH_PATTERN = "hcc-team-weekly-report"


def _friday_of_week(d=None):
    """Calculate the Friday of the current reporting week.

    Thursday through Saturday map to the same-week Friday.
    Sunday maps to the previous Friday (completed week).
    """
    if d is None:
        d = date.today()
    weekday = d.weekday()  # Monday=0 ... Sunday=6
    if weekday == 6:  # Sunday
        return d - timedelta(days=2)
    days_until_friday = 4 - weekday
    return d + timedelta(days=days_until_friday)


def _gh_json(args):
    """Run a gh CLI command and return parsed JSON, or None on failure."""
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
    """Find an open or merged PR for this week's report."""
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
    """Check if any review has CHANGES_REQUESTED state."""
    reviews = pr.get("reviews", [])
    return any(r.get("state") == "CHANGES_REQUESTED" for r in reviews)


def _get_review_comments(pr):
    """Fetch review comments on the PR."""
    number = pr.get("number")
    if not number:
        return []
    comments = _gh_json([
        "pr", "view", str(number),
        "--repo", UPSTREAM_REPO,
        "--json", "comments,reviews",
    ])
    if not comments:
        return []

    result = []
    for review in comments.get("reviews", []):
        body = review.get("body", "").strip()
        if body:
            result.append({
                "author": review.get("author", {}).get("login", "unknown"),
                "state": review.get("state", ""),
                "body": body,
            })
    for comment in comments.get("comments", []):
        body = comment.get("body", "").strip()
        if body:
            result.append({
                "author": comment.get("author", {}).get("login", "unknown"),
                "body": body,
            })
    return result


def check_weekly_report():
    """Check weekly report readiness. Returns (should_run, task_name, content) or (False, None, reason)."""
    today = date.today()
    weekday = today.weekday()  # Monday=0, Tuesday=1, Wednesday=2

    if weekday not in (1, 2):  # Only Tuesday and Wednesday
        return False, None, "Not Tuesday or Wednesday"

    friday = _friday_of_week(today)
    friday_str = friday.isoformat()

    pr = _find_weekly_pr(friday_str)

    if pr is None:
        if weekday == 1:  # Tuesday, no PR — generate
            content = (
                f"## TASK: weekly-report-generate\n\n"
                f"Generate HCC weekly status reports for week ending {friday_str}.\n\n"
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
    comments = _get_review_comments(pr)
    has_feedback = len(comments) > 0

    if has_feedback and _has_changes_requested(pr):
        feedback_text = "\n".join(
            f"- **{c['author']}** ({c.get('state', 'comment')}): {c['body'][:200]}"
            for c in comments
        )
        content = (
            f"## TASK: weekly-report-feedback\n\n"
            f"Address review feedback on PR #{pr_number}.\n\n"
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
                f"- **PR**: {pr_url}\n"
                f"- **Branch**: {pr.get('headRefName', '?')}\n"
                f"- **Friday date**: {friday_str}\n\n"
                f"### Review Comments\n\n{feedback_text}\n"
            )
            return True, "weekly-report-feedback", content

        content = (
            f"## TASK: weekly-report-merge\n\n"
            f"Merge the weekly report PR — no blocking reviews.\n\n"
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
        "days": [1, 2],  # Tuesday, Wednesday
        "check": check_weekly_report,
    },
    # Future tasks:
    # {"name": "jira-cleanup", "days": [3], "check": check_jira_cleanup},
]


def main():
    today = date.today()
    weekday = today.weekday()

    for task in TASKS:
        if weekday not in task["days"]:
            continue

        should_run, task_name, content = task["check"]()

        if should_run:
            print(
                f"Dispatching task: {task_name}",
                file=sys.stderr,
            )
            json.dump(
                {"status": "start", "content": content},
                sys.stdout,
            )
            return

        print(
            f"Task {task['name']} skipped: {content}",
            file=sys.stderr,
        )

    json.dump(
        {"status": "skip", "content": f"No tasks to run today ({today.strftime('%A')})"},
        sys.stdout,
    )


if __name__ == "__main__":
    main()
