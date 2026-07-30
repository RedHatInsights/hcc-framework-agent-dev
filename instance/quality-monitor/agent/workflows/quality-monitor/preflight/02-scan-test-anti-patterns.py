#!/usr/bin/env python3
"""Scan repos for test anti-patterns - runs once daily (KEDA scheduled)."""

import subprocess
from datetime import datetime
from pathlib import Path

from common import (
    load_project_repos,
    output_result,
    get_capacity,
    get_tasks,
    load_state,
    save_state,
)


def find_test_files(repo_path, max_files=20):
    """Find test files in repository."""
    test_files = []

    # Common test file patterns
    test_patterns = [
        "**/*.test.js",
        "**/*.test.ts",
        "**/*.test.jsx",
        "**/*.test.tsx",
        "**/*.spec.js",
        "**/*.spec.ts",
        "**/*.spec.jsx",
        "**/*.spec.tsx",
        "**/test_*.py",
        "**/*_test.py",
        "**/*Test.java",
    ]

    for pattern in test_patterns:
        for file_path in repo_path.glob(pattern):
            if file_path.is_file() and len(test_files) < max_files:
                # Get relative path and check size
                rel_path = file_path.relative_to(repo_path)
                file_size = file_path.stat().st_size

                # Skip very large files (>100KB)
                if file_size > 100_000:
                    continue

                test_files.append({
                    "path": str(rel_path),
                    "full_path": str(file_path),
                    "size": file_size,
                })

    return test_files[:max_files]


def main():
    # Only run once per day (KEDA controls pod scheduling)
    state = load_state()
    last_scan_date = state.get("last_anti_pattern_scan", "")
    today = datetime.now().strftime("%Y-%m-%d")

    if last_scan_date == today:
        output_result("skip", f"Already scanned today ({today})")
        return

    # Check capacity
    active_n, max_n = get_capacity()
    if active_n >= max_n:
        output_result("skip", f"At capacity ({active_n}/{max_n})")
        return

    # Check for existing test scan tasks
    tasks = get_tasks()
    active_scans = [
        t
        for t in tasks
        if t.get("external_key", "").startswith("test-scan:")
        and t.get("status") in ("in_progress", "pr_open", "pr_changes")
    ]
    if len(active_scans) >= 5:
        output_result("skip", f"Already processing {len(active_scans)} test scans")
        return

    repos = load_project_repos()
    repos_with_tests = {}

    # Limit to 3 repos per run to keep prompt manageable
    for repo_name in list(repos.keys())[:3]:
        repo_path = Path("repos") / repo_name

        if not repo_path.exists():
            # Clone shallow for speed
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "--depth",
                        "1",
                        repos[repo_name]["upstream"],
                        str(repo_path),
                    ],
                    capture_output=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                continue

        # Find test files
        test_files = find_test_files(repo_path, max_files=10)
        if test_files:
            repos_with_tests[repo_name] = test_files

    # Mark as scanned today
    save_state({"last_anti_pattern_scan": today})

    if not repos_with_tests:
        output_result("skip", f"Scanned {min(3, len(repos))} repos, no test files found")
        return

    # Format for AI - just list the files to analyze
    total_files = sum(len(files) for files in repos_with_tests.values())
    content = f"# Test Anti-Pattern Scan\n\n"
    content += f"Found {total_files} test files across {len(repos_with_tests)} repositories.\n\n"
    content += f"**Instructions:**\n"
    content += f"1. Read `instance/quality-monitor/agent/workflows/quality-monitor/anti-patterns.yaml` for pattern definitions\n"
    content += f"2. Analyze the test files below for those patterns\n"
    content += f"3. Focus on HIGH severity patterns first\n"
    content += f"4. Use the examples in anti-patterns.yaml to guide your analysis\n\n"

    for repo, test_files in repos_with_tests.items():
        content += f"## {repo} ({len(test_files)} test files)\n\n"
        for test_file in test_files:
            content += f"- `{test_file['path']}` ({test_file['size']} bytes)\n"
        content += "\n"

    content += f"\n**Next steps:**\n"
    content += f"1. Read anti-patterns.yaml\n"
    content += f"2. Read a sample of the test files listed above\n"
    content += f"3. Identify any anti-patterns based on the definitions\n"
    content += f"4. Create GitHub issues and notifications per workflow CLAUDE.md\n"

    output_result("start", content)


if __name__ == "__main__":
    main()
