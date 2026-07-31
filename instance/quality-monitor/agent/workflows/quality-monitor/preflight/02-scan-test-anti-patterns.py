#!/usr/bin/env python3
"""Scan repos for test anti-patterns - runs once daily (KEDA scheduled)."""

import subprocess
import yaml
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


def load_test_config():
    """Load test file configuration."""
    config_path = Path(__file__).parent.parent / "test-config.yaml"
    if not config_path.exists():
        return None

    with open(config_path) as f:
        return yaml.safe_load(f)


def detect_framework(repo_path, config):
    """Auto-detect test framework based on indicators."""
    if not config or "defaults" not in config:
        return None

    framework_detection = config["defaults"].get("framework_detection", {})

    for framework, detection in framework_detection.items():
        indicators = detection.get("indicators", [])
        for indicator in indicators:
            # Check for exact file or glob pattern
            if "*" in indicator:
                if list(repo_path.glob(indicator)):
                    return framework
            else:
                if (repo_path / indicator).exists():
                    return framework

    return None


def get_test_patterns(repo_name, repo_path, config):
    """Get test file patterns for a repo (custom or auto-detected)."""
    if not config:
        # Fallback to hardcoded patterns
        return [
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
        ], []

    # Check for repo-specific config
    repos_config = config.get("repos") if config else None
    if repos_config and repo_name in repos_config:
        repo_cfg = repos_config[repo_name]
        return repo_cfg.get("patterns", []), repo_cfg.get("exclude", [])

    # Auto-detect framework
    framework = detect_framework(repo_path, config)

    defaults = config.get("defaults", {})
    global_excludes = defaults.get("global_excludes", [])

    if framework:
        framework_config = defaults.get("framework_detection", {}).get(framework, {})
        patterns = framework_config.get("patterns", [])
        return patterns, global_excludes

    # Use generic fallback
    generic_patterns = defaults.get("generic_patterns", [])
    return generic_patterns, global_excludes


def expand_brace_patterns(pattern):
    """Expand {a,b,c} patterns into multiple patterns."""
    import re

    match = re.search(r"\{([^}]+)\}", pattern)
    if not match:
        return [pattern]

    options = match.group(1).split(",")
    results = []
    for option in options:
        expanded = pattern[: match.start()] + option + pattern[match.end() :]
        # Recursively expand if more braces exist
        results.extend(expand_brace_patterns(expanded))
    return results


def find_test_files(repo_path, repo_name, config, max_files=20):
    """Find test files in repository using config or auto-detection."""
    test_files = []

    patterns, excludes = get_test_patterns(repo_name, repo_path, config)

    # Expand brace patterns
    expanded_patterns = []
    for pattern in patterns:
        expanded_patterns.extend(expand_brace_patterns(pattern))

    for pattern in expanded_patterns:
        for file_path in repo_path.glob(pattern):
            if not file_path.is_file():
                continue

            if len(test_files) >= max_files:
                break

            # Check excludes
            rel_path = file_path.relative_to(repo_path)
            excluded = False
            for exclude_pattern in excludes:
                if file_path.match(exclude_pattern):
                    excluded = True
                    break

            if excluded:
                continue

            file_size = file_path.stat().st_size

            # Skip very large files
            limits = config.get("limits", {}) if config else {}
            max_size = limits.get("max_file_size_bytes", 102400)
            if file_size > max_size:
                continue

            test_files.append(
                {
                    "path": str(rel_path),
                    "full_path": str(file_path),
                    "size": file_size,
                }
            )

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

    # Load test config
    test_config = load_test_config()
    max_repos = (
        test_config.get("limits", {}).get("max_repos_per_scan", 3) if test_config else 3
    )

    repos = load_project_repos()
    repos_with_tests = {}

    # Limit repos per run
    for repo_name in list(repos.keys())[:max_repos]:
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

        # Find test files using config or auto-detection
        test_files = find_test_files(repo_path, repo_name, test_config)
        if test_files:
            # Detect framework for informational purposes
            framework = (
                detect_framework(repo_path, test_config) if test_config else "unknown"
            )
            repos_with_tests[repo_name] = {
                "files": test_files,
                "framework": framework or "generic",
            }

    # Mark as scanned today
    save_state({"last_anti_pattern_scan": today})

    if not repos_with_tests:
        output_result(
            "skip", f"Scanned {min(max_repos, len(repos))} repos, no test files found"
        )
        return

    # Format for AI - just list the files to analyze
    total_files = sum(len(data["files"]) for data in repos_with_tests.values())
    content = f"# Test Anti-Pattern Scan\n\n"
    content += f"Found {total_files} test files across {len(repos_with_tests)} repositories.\n\n"
    content += f"**Instructions:**\n"
    content += f"1. Read `instance/quality-monitor/agent/workflows/quality-monitor/anti-patterns.yaml` for pattern definitions\n"
    content += f"2. Analyze the test files below for those patterns\n"
    content += f"3. Focus on HIGH severity patterns first\n"
    content += f"4. Use the examples in anti-patterns.yaml to guide your analysis\n\n"

    for repo, data in repos_with_tests.items():
        test_files = data["files"]
        framework = data["framework"]
        content += (
            f"## {repo} ({len(test_files)} test files, framework: {framework})\n\n"
        )
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
