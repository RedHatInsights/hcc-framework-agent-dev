#!/usr/bin/env python3
"""Manual test runner for merge violation checker.

MANUAL TESTING ONLY - not used by the bot workflow.
Run locally to validate merge checker behavior against real repositories.
Requires GH_TOKEN environment variable or gh CLI authentication.
"""

import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Import checker functions
sys.path.insert(0, str(Path(__file__).parent))

# Import after path setup
from importlib import util
spec = util.spec_from_file_location("checker", "01-check-merged-prs.py")
checker = util.module_from_spec(spec)

# Mock common module before loading checker
from unittest.mock import Mock
mock_common = Mock()
sys.modules['common'] = mock_common

# Now execute the module
spec.loader.exec_module(checker)


def get_repo_remote(repo_path: Path) -> str:
    """Get the upstream GitHub URL for a repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "upstream"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()

        # Try origin if no upstream
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()

    except subprocess.TimeoutExpired:
        pass

    return None


def extract_org_repo(url: str) -> str:
    """Extract org/repo from GitHub URL."""
    if not url:
        return None

    # Handle both SSH and HTTPS URLs
    if "github.com" in url:
        # git@github.com:RedHatInsights/landing-page-frontend.git -> RedHatInsights/landing-page-frontend
        # https://github.com/RedHatInsights/landing-page-frontend.git -> RedHatInsights/landing-page-frontend
        parts = url.replace(":", "/").replace(".git", "").split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"

    return None


def test_repo(repo_path: str, limit: int = 10):
    """Test the merge checker against a specific repository."""
    repo_path = Path(repo_path).expanduser()

    if not repo_path.exists():
        print(f"❌ Repository not found: {repo_path}")
        return

    print(f"\n🔍 Testing merge violation checker on: {repo_path}")
    print("=" * 80)

    # Get GitHub repo info
    remote_url = get_repo_remote(repo_path)
    if not remote_url:
        print("❌ Could not find git remote (upstream or origin)")
        return

    org_repo = extract_org_repo(remote_url)
    if not org_repo:
        print(f"❌ Could not parse GitHub org/repo from: {remote_url}")
        return

    print(f"📦 Repository: {org_repo}")
    print(f"🔗 Remote: {remote_url}")

    # Get recent merged PRs
    print(f"\n📋 Fetching last {limit} merged PRs...")

    try:
        result = subprocess.run(
            [
                "gh", "pr", "list",
                "--repo", org_repo,
                "--state", "merged",
                "--limit", str(limit),
                "--json", "number,title,url,author,mergedAt"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"❌ gh CLI error: {result.stderr}")
            return

        prs = json.loads(result.stdout)

        if not prs:
            print("  (no merged PRs found)")
            return

        print(f"\n✅ Found {len(prs)} merged PRs")

        # Check last 24 hours
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_prs = [
            pr for pr in prs
            if datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00")) > since
        ]

        print(f"📅 {len(recent_prs)} merged in last 24 hours\n")

        # Check each PR for violations
        violations = []

        for pr in prs:
            pr_num = pr["number"]
            merged_at = pr["mergedAt"]

            # Check if recent
            is_recent = datetime.fromisoformat(merged_at.replace("Z", "+00:00")) > since
            age_marker = "🕐" if is_recent else "⏰"

            print(f"{age_marker} PR #{pr_num}: {pr['title'][:60]}")
            print(f"   Author: {pr['author']['login']}, Merged: {merged_at}")

            # Check for violations
            violation = checker.check_pr_violations(org_repo, pr_num, pr)

            if violation:
                violations.append(violation)
                severity_icon = "🔴" if any(c["conclusion"] == "FAILURE" for c in violation["failed_checks"]) else "🟡"
                print(f"   {severity_icon} VIOLATION: {len(violation['failed_checks'])} failed checks")
                for check in violation["failed_checks"]:
                    print(f"      - {check['name']}: {check['conclusion']}")
            else:
                print(f"   ✅ All checks passed")

            print()

        # Summary
        print("=" * 80)
        if violations:
            print(f"⚠️  Found {len(violations)} PRs merged with failed checks:\n")
            for v in violations:
                has_failure = any(c["conclusion"] == "FAILURE" for c in v["failed_checks"])
                has_cancelled = any(c["conclusion"] == "CANCELLED" for c in v["failed_checks"])
                severity = "HIGH" if has_failure else "MEDIUM" if has_cancelled else "LOW"
                print(f"  [{severity}] PR #{v['number']}: {v['title']}")
                print(f"         {v['url']}")
                for check in v["failed_checks"]:
                    print(f"         - {check['name']}: {check['conclusion']}")
                print()
        else:
            print("✅ No merge violations found - all PRs passed their checks!\n")

    except subprocess.TimeoutExpired:
        print("❌ Timeout fetching PR data")
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_merge_checker.py <repo_path> [limit]")
        print("\nExamples:")
        print("  python test_merge_checker.py ~/repos/js/landing-page-frontend")
        print("  python test_merge_checker.py ~/repos/js/insights-chrome 20")
        sys.exit(1)

    repo = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    test_repo(repo, limit)
