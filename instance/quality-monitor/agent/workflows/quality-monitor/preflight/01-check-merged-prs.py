#!/usr/bin/env python3
"""Check for merged PRs with failed checks - runs once daily (KEDA scheduled)."""

import subprocess
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import (
    load_project_repos,
    upstream_repo,
    output_result,
    get_capacity,
    get_tasks,
    load_state,
    save_state,
)


def check_pr_violations(org_repo, pr_number, pr_data):
    """Check if PR has check violations."""
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--repo",
                org_repo,
                "--json",
                "statusCheckRollup",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return None

        data = json.loads(result.stdout)
        rollup = data.get("statusCheckRollup", [])

        failed_checks = [
            {
                "name": check.get("name"),
                "conclusion": check.get("conclusion"),
                "url": check.get("detailsUrl", ""),
            }
            for check in rollup
            if check.get("conclusion") in ["FAILURE", "SKIPPED", "CANCELLED"]
        ]

        if failed_checks:
            return {
                "number": pr_data["number"],
                "title": pr_data["title"],
                "url": pr_data["url"],
                "author": pr_data.get("author", {}).get("login", "unknown"),
                "merged_at": pr_data["mergedAt"],
                "failed_checks": failed_checks,
            }

        return None

    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def main():
    # Only run once per day (KEDA controls pod scheduling)
    state = load_state()
    last_scan_date = state.get("last_merge_check_scan", "")
    today = datetime.now().strftime("%Y-%m-%d")

    if last_scan_date == today:
        output_result("skip", f"Already scanned today ({today})")
        return

    # Check capacity
    active_n, max_n = get_capacity()
    if active_n >= max_n:
        output_result("skip", f"At capacity ({active_n}/{max_n})")
        return

    # Check for existing merge violation tasks
    tasks = get_tasks()
    active_violations = [
        t
        for t in tasks
        if t.get("external_key", "").startswith("merge-violation:")
        and t.get("status") in ("in_progress", "pr_open", "pr_changes")
    ]
    if len(active_violations) >= 5:
        output_result("skip", f"Already processing {len(active_violations)} violations")
        return

    repos = load_project_repos()
    violations = {}
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    for repo_name in repos.keys():
        upstream, host = upstream_repo(repo_name)
        if not upstream or host != "github":
            continue

        try:
            # Get recent merges
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    upstream,
                    "--state",
                    "merged",
                    "--limit",
                    "50",
                    "--json",
                    "number,title,url,author,mergedAt",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                continue

            prs = json.loads(result.stdout)
            recent_prs = [
                pr
                for pr in prs
                if datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00")) > since
            ]

            # Check each PR
            repo_violations = []
            for pr in recent_prs:
                violation = check_pr_violations(upstream, pr["number"], pr)
                if violation:
                    repo_violations.append(violation)

            if repo_violations:
                violations[repo_name] = repo_violations

        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            continue

    # Mark as scanned today
    save_state({"last_merge_check_scan": today})

    if not violations:
        output_result("skip", "No merged PRs with failed checks in last 24h")
        return

    # Format for AI
    total = sum(len(v) for v in violations.values())
    content = f"# Merge-Without-Checks Violations\n\n"
    content += f"Found {total} PRs merged with failed checks across {len(violations)} repositories:\n\n"

    for repo, prs in violations.items():
        content += f"## {repo} ({len(prs)} violations)\n\n"
        for pr in prs:
            # Determine severity
            has_failure = any(c["conclusion"] == "FAILURE" for c in pr["failed_checks"])
            has_cancelled = any(
                c["conclusion"] == "CANCELLED" for c in pr["failed_checks"]
            )
            severity = "HIGH" if has_failure else "MEDIUM" if has_cancelled else "LOW"

            content += f"### PR #{pr['number']}: {pr['title']} [**{severity}**]\n"
            content += f"- **URL:** {pr['url']}\n"
            content += f"- **Author:** @{pr['author']}\n"
            content += f"- **Merged:** {pr['merged_at']}\n"
            content += f"- **Failed checks:**\n"
            for check in pr["failed_checks"]:
                content += f"  - `{check['name']}`: {check['conclusion']}\n"
                if check.get("url"):
                    content += f"    - Details: {check['url']}\n"
            content += "\n"

    output_result("start", content)


if __name__ == "__main__":
    main()
