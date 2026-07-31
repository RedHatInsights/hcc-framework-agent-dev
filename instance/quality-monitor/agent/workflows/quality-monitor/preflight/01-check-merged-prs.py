#!/usr/bin/env python3
"""Check for merged PRs with failed checks - runs once daily (KEDA scheduled)."""

import subprocess
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from common import (
    load_project_repos,
    upstream_repo,
    output_result,
    get_capacity,
    get_tasks,
    load_state,
    save_state,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Timeout constants (seconds)
TIMEOUT_PR_VIEW = 10  # Individual PR check status
TIMEOUT_PR_LIST = 30  # List merged PRs
MAX_PRS_PER_REPO = 50  # Limit PRs fetched per repo
MAX_CONCURRENT_VIOLATIONS = 5  # Max violations to process at once


def parse_merged_at(merged_at_str: Optional[str]) -> Optional[datetime]:
    """Safely parse GitHub mergedAt timestamp.

    Args:
        merged_at_str: ISO format timestamp from GitHub API

    Returns:
        Timezone-aware datetime or None if invalid
    """
    if not merged_at_str:
        return None
    try:
        return datetime.fromisoformat(merged_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError) as e:
        logger.warning(f"Invalid mergedAt format: {merged_at_str} - {e}")
        return None


def extract_pr_metadata(pr_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract relevant PR metadata safely.

    Args:
        pr_data: PR data from GitHub API

    Returns:
        Dict with extracted metadata fields
    """
    return {
        "number": pr_data.get("number"),
        "title": pr_data.get("title", ""),
        "url": pr_data.get("url", ""),
        "author": pr_data.get("author", {}).get("login", "unknown"),
        "merged_at": pr_data.get("mergedAt"),
    }


def check_pr_violations(
    org_repo: str, pr_number: int, pr_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Check if PR has check violations.

    Args:
        org_repo: Repository in 'owner/repo' format
        pr_number: Pull request number
        pr_data: PR metadata from GitHub API

    Returns:
        Violation dict if failed checks found, None otherwise
    """
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
            timeout=TIMEOUT_PR_VIEW,
        )

        if result.returncode != 0:
            logger.warning(
                f"gh CLI failed for {org_repo}#{pr_number}: {result.stderr.strip()}"
            )
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
            metadata = extract_pr_metadata(pr_data)
            return {
                **metadata,
                "failed_checks": failed_checks,
            }

        return None

    except subprocess.TimeoutExpired:
        logger.warning(
            f"Timeout checking {org_repo}#{pr_number} after {TIMEOUT_PR_VIEW}s"
        )
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON from gh CLI for {org_repo}#{pr_number}: {e}")
        return None


def main():
    """Main entry point for merge violation checker."""
    # Only run once per day (KEDA controls pod scheduling)
    state = load_state()
    last_scan_date = state.get("last_merge_check_scan", "")
    today = datetime.now().strftime("%Y-%m-%d")

    if last_scan_date == today:
        logger.info(f"Already scanned today ({today})")
        output_result("skip", f"Already scanned today ({today})")
        return

    # Check capacity
    active_n, max_n = get_capacity()
    if active_n >= max_n:
        logger.info(f"At capacity ({active_n}/{max_n})")
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
    if len(active_violations) >= MAX_CONCURRENT_VIOLATIONS:
        logger.info(f"Already processing {len(active_violations)} violations")
        output_result("skip", f"Already processing {len(active_violations)} violations")
        return

    repos = load_project_repos()
    violations: Dict[str, List[Dict[str, Any]]] = {}
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    logger.info(
        f"Checking {len(repos)} repositories for merge violations since {since}"
    )

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
                    str(MAX_PRS_PER_REPO),
                    "--json",
                    "number,title,url,author,mergedAt",
                ],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_PR_LIST,
            )

            if result.returncode != 0:
                logger.warning(f"gh CLI failed for {upstream}: {result.stderr.strip()}")
                continue

            prs = json.loads(result.stdout)

            # Filter to recent PRs with validated timestamps
            recent_prs = []
            for pr in prs:
                merged_at = parse_merged_at(pr.get("mergedAt"))
                if merged_at and merged_at > since:
                    recent_prs.append(pr)

            logger.info(f"{upstream}: {len(recent_prs)} PRs merged in last 24h")

            # Check each PR
            repo_violations = []
            for pr in recent_prs:
                violation = check_pr_violations(upstream, pr["number"], pr)
                if violation:
                    repo_violations.append(violation)

            if repo_violations:
                violations[repo_name] = repo_violations
                logger.info(f"{upstream}: Found {len(repo_violations)} violations")

        except subprocess.TimeoutExpired:
            logger.warning(
                f"Timeout listing PRs for {upstream} after {TIMEOUT_PR_LIST}s"
            )
            continue
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from gh CLI for {upstream}: {e}")
            continue

    # Mark as scanned today
    save_state({"last_merge_check_scan": today})

    if not violations:
        logger.info("No merged PRs with failed checks in last 24h")
        output_result("skip", "No merged PRs with failed checks in last 24h")
        return

    total_violations = sum(len(v) for v in violations.values())
    logger.info(
        f"Found {total_violations} violations across {len(violations)} repositories"
    )

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
