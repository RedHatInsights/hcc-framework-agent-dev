#!/usr/bin/env python3
"""Scan repos for test anti-patterns - runs once daily (KEDA scheduled)."""

import subprocess
import yaml
import logging
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from itertools import islice
from typing import Optional, Dict, Any, List, Tuple

from common import (
    load_project_repos,
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

# Timeout and limit constants
TIMEOUT_GIT_CLONE = 120  # seconds - shallow clone timeout
MAX_TEST_FILES_PER_REPO = 20  # Max test files to analyze per repo
MAX_CONCURRENT_SCANS = 5  # Max test scan tasks to process at once
DEFAULT_MAX_REPOS_PER_SCAN = 3  # Default repos to scan per run
DEFAULT_MAX_FILE_SIZE = 102400  # 100KB default max file size


def load_test_config() -> Optional[Dict[str, Any]]:
    """Load test file configuration.

    Returns:
        Config dict or None if file doesn't exist
    """
    config_path = Path(__file__).parent.parent / "test-config.yaml"
    if not config_path.exists():
        logger.warning(f"Test config not found at {config_path}")
        return None

    try:
        with open(config_path) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse test config: {e}")
        return None


def detect_framework(repo_path: Path, config: Optional[Dict]) -> Optional[str]:
    """Auto-detect test framework based on indicators.

    Args:
        repo_path: Path to repository
        config: Test configuration dict

    Returns:
        Framework name or None if not detected
    """
    if not config or "defaults" not in config:
        return None

    framework_detection = config["defaults"].get("framework_detection", {})

    for framework, detection in framework_detection.items():
        indicators = detection.get("indicators", [])
        for indicator in indicators:
            # Check for exact file or glob pattern
            if "*" in indicator:
                if list(repo_path.glob(indicator)):
                    logger.debug(f"Detected {framework} via glob pattern {indicator}")
                    return framework
            else:
                if (repo_path / indicator).exists():
                    logger.debug(f"Detected {framework} via file {indicator}")
                    return framework

    return None


def get_test_patterns(
    repo_name: str, repo_path: Path, config: Optional[Dict]
) -> Tuple[List[str], List[str]]:
    """Get test file patterns for a repo (custom or auto-detected).

    Args:
        repo_name: Repository name
        repo_path: Path to repository
        config: Test configuration dict

    Returns:
        Tuple of (patterns, excludes) lists
    """
    if not config:
        # Fallback to hardcoded patterns
        logger.debug(f"{repo_name}: Using fallback patterns (no config)")
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
        logger.info(f"{repo_name}: Using repo-specific config")
        return repo_cfg.get("patterns", []), repo_cfg.get("exclude", [])

    # Auto-detect framework
    framework = detect_framework(repo_path, config)

    defaults = config.get("defaults", {})
    global_excludes = defaults.get("global_excludes", [])

    if framework:
        framework_config = defaults.get("framework_detection", {}).get(framework, {})
        patterns = framework_config.get("patterns", [])
        logger.info(f"{repo_name}: Detected {framework}, using framework patterns")
        return patterns, global_excludes

    # Use generic fallback
    generic_patterns = defaults.get("generic_patterns", [])
    logger.info(f"{repo_name}: No framework detected, using generic patterns")
    return generic_patterns, global_excludes


def expand_brace_patterns(pattern: str) -> List[str]:
    """Expand {a,b,c} patterns into multiple patterns.

    Args:
        pattern: Glob pattern potentially containing braces

    Returns:
        List of expanded patterns
    """
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


def find_test_files(
    repo_path: Path,
    repo_name: str,
    config: Optional[Dict],
    max_files: int = MAX_TEST_FILES_PER_REPO,
) -> List[Dict[str, Any]]:
    """Find test files in repository using config or auto-detection.

    Args:
        repo_path: Path to repository
        repo_name: Repository name
        config: Test configuration dict
        max_files: Maximum files to return

    Returns:
        List of dicts with path, full_path, size
    """
    test_files = []

    patterns, excludes = get_test_patterns(repo_name, repo_path, config)

    # Expand brace patterns
    expanded_patterns = []
    for pattern in patterns:
        expanded_patterns.extend(expand_brace_patterns(pattern))

    logger.debug(f"{repo_name}: Searching with {len(expanded_patterns)} patterns")

    # Get file size limit
    limits = config.get("limits", {}) if config else {}
    max_size = limits.get("max_file_size_bytes", DEFAULT_MAX_FILE_SIZE)

    for pattern in expanded_patterns:
        # Calculate remaining slots
        remaining = max_files - len(test_files)
        if remaining <= 0:
            break

        # Use islice to limit glob iteration
        for file_path in islice(repo_path.glob(pattern), remaining):
            if not file_path.is_file():
                continue

            # Check excludes
            excluded = False
            for exclude_pattern in excludes:
                if file_path.match(exclude_pattern):
                    excluded = True
                    break

            if excluded:
                continue

            file_size = file_path.stat().st_size

            # Skip very large files
            if file_size > max_size:
                logger.debug(
                    f"{repo_name}: Skipping large file {file_path} ({file_size} bytes)"
                )
                continue

            rel_path = file_path.relative_to(repo_path)
            test_files.append(
                {
                    "path": str(rel_path),
                    "full_path": str(file_path),
                    "size": file_size,
                }
            )

    logger.info(f"{repo_name}: Found {len(test_files)} test files")
    return test_files


def clone_repository(upstream_url: str, dest_path: Path) -> bool:
    """Clone repository with timeout and error handling.

    Args:
        upstream_url: Repository URL to clone
        dest_path: Destination path for clone

    Returns:
        True if successful, False otherwise
    """
    try:
        result = subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                upstream_url,
                str(dest_path),
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_GIT_CLONE,
        )
        if result.returncode != 0:
            logger.warning(
                f"git clone failed for {upstream_url}: {result.stderr.strip()}"
            )
            return False
        logger.info(f"Cloned {upstream_url} to {dest_path}")
        return True
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout cloning {upstream_url} after {TIMEOUT_GIT_CLONE}s")
        return False


def main():
    """Main entry point for test anti-pattern scanner."""
    # Only run once per day (KEDA controls pod scheduling)
    state = load_state()
    last_scan_date = state.get("last_anti_pattern_scan", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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

    # Check for existing test scan tasks
    tasks = get_tasks()
    active_scans = [
        t
        for t in tasks
        if t.get("external_key", "").startswith("test-scan:")
        and t.get("status") in ("in_progress", "pr_open", "pr_changes")
    ]
    if len(active_scans) >= MAX_CONCURRENT_SCANS:
        logger.info(f"Already processing {len(active_scans)} test scans")
        output_result("skip", f"Already processing {len(active_scans)} test scans")
        return

    # Load test config
    test_config = load_test_config()
    max_repos = (
        test_config.get("limits", {}).get(
            "max_repos_per_scan", DEFAULT_MAX_REPOS_PER_SCAN
        )
        if test_config
        else DEFAULT_MAX_REPOS_PER_SCAN
    )

    repos = load_project_repos()
    repos_with_tests: Dict[str, Dict[str, Any]] = {}

    # Filter repos if scan_only_repos is configured
    scan_only = test_config.get("scan_only_repos") if test_config else None
    if scan_only:
        logger.info(f"Filtering to scan_only_repos: {scan_only}")
        repos = {k: v for k, v in repos.items() if k in scan_only}
        if not repos:
            logger.warning("No repos match scan_only_repos filter")
            output_result("skip", "No repositories configured in scan_only_repos")
            return

    # Use temp directory for clones (automatic cleanup)
    temp_dir = None
    try:
        temp_dir = Path(tempfile.mkdtemp(prefix="quality-scan-"))
        logger.info(f"Using temporary directory: {temp_dir}")

        # Limit repos per run
        repo_list = list(repos.keys())[:max_repos]
        logger.info(f"Scanning {len(repo_list)} repositories for test files")

        for repo_name in repo_list:
            repo_path = temp_dir / repo_name

            # Clone repository
            upstream_url = repos[repo_name].get("upstream")
            if not upstream_url:
                logger.warning(f"{repo_name}: No upstream URL configured")
                continue

            if not clone_repository(upstream_url, repo_path):
                continue

            # Find test files using config or auto-detection
            test_files = find_test_files(repo_path, repo_name, test_config)
            if test_files:
                # Detect framework for informational purposes
                framework = (
                    detect_framework(repo_path, test_config)
                    if test_config
                    else "unknown"
                )
                repos_with_tests[repo_name] = {
                    "files": test_files,
                    "framework": framework or "generic",
                }

    finally:
        # Clean up temporary directory
        if temp_dir and temp_dir.exists():
            logger.info(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir, ignore_errors=True)

    # Mark as scanned today
    save_state({"last_anti_pattern_scan": today})

    if not repos_with_tests:
        logger.info(f"Scanned {min(max_repos, len(repos))} repos, no test files found")
        output_result(
            "skip", f"Scanned {min(max_repos, len(repos))} repos, no test files found"
        )
        return

    total_files = sum(len(data["files"]) for data in repos_with_tests.values())
    logger.info(
        f"Found {total_files} test files across {len(repos_with_tests)} repositories"
    )

    # Format for AI - compact format without redundant instructions
    # (Workflow CLAUDE.md already contains the instructions)
    total_files = sum(len(data["files"]) for data in repos_with_tests.values())
    content = f"# Test Files for Anti-Pattern Analysis ({total_files} files)\n\n"

    for repo, data in repos_with_tests.items():
        test_files = data["files"]
        framework = data["framework"]

        # Compact format: comma-separated file list
        file_list = ", ".join(f["path"] for f in test_files)

        content += f"{repo} ({len(test_files)} files, {framework}):\n"
        content += f"  {file_list}\n\n"

    output_result("start", content)


if __name__ == "__main__":
    main()
