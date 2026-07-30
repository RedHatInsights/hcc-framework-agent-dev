#!/usr/bin/env python3
"""Tests for 01-check-merged-prs.py preflight script."""

import pytest
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def mock_common_module():
    """Mock the common module that preflight scripts depend on."""
    mock_common = Mock()
    mock_common.load_project_repos = Mock(return_value={})
    mock_common.upstream_repo = Mock(return_value=("RedHatInsights/test-repo", "github"))
    mock_common.output_result = Mock()
    mock_common.get_capacity = Mock(return_value=(0, 10))
    mock_common.get_tasks = Mock(return_value=[])
    mock_common.load_state = Mock(return_value={})
    mock_common.save_state = Mock()

    sys.modules['common'] = mock_common

    yield mock_common

    # Cleanup
    if 'common' in sys.modules:
        del sys.modules['common']


# Import after mocking common
import importlib

spec = importlib.util.spec_from_file_location(
    "check_merged_prs",
    Path(__file__).parent.parent / "01-check-merged-prs.py"
)
check_module = importlib.util.module_from_spec(spec)


@pytest.fixture
def sample_pr_data():
    """Sample PR data matching gh CLI output format."""
    return {
        "number": 123,
        "title": "Fix critical bug",
        "url": "https://github.com/RedHatInsights/test-repo/pull/123",
        "author": {"login": "developer"},
        "mergedAt": datetime.now().isoformat() + "Z"
    }


@pytest.fixture
def sample_status_checks():
    """Sample status check rollup data."""
    return {
        "statusCheckRollup": [
            {
                "name": "ci/test",
                "conclusion": "SUCCESS",
                "detailsUrl": "https://github.com/actions/runs/123"
            },
            {
                "name": "ci/lint",
                "conclusion": "FAILURE",
                "detailsUrl": "https://github.com/actions/runs/124"
            },
            {
                "name": "ci/build",
                "conclusion": "CANCELLED",
                "detailsUrl": "https://github.com/actions/runs/125"
            }
        ]
    }


class TestCheckPrViolations:
    """Tests for check_pr_violations function."""

    def test_detects_failed_checks(self, sample_pr_data, sample_status_checks):
        """Detects PRs with failed status checks."""
        spec.loader.exec_module(check_module)

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(sample_status_checks)

        with patch('subprocess.run', return_value=mock_result):
            result = check_module.check_pr_violations(
                "RedHatInsights/test-repo",
                123,
                sample_pr_data
            )

        assert result is not None
        assert result["number"] == 123
        assert result["title"] == "Fix critical bug"
        assert len(result["failed_checks"]) == 2  # FAILURE and CANCELLED

        # Verify failed checks
        failed_names = {c["name"] for c in result["failed_checks"]}
        assert "ci/lint" in failed_names
        assert "ci/build" in failed_names

    def test_detects_skipped_checks(self, sample_pr_data):
        """Detects PRs with skipped status checks."""
        spec.loader.exec_module(check_module)

        status_with_skip = {
            "statusCheckRollup": [
                {
                    "name": "optional-check",
                    "conclusion": "SKIPPED",
                    "detailsUrl": "https://github.com/actions/runs/126"
                }
            ]
        }

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(status_with_skip)

        with patch('subprocess.run', return_value=mock_result):
            result = check_module.check_pr_violations(
                "RedHatInsights/test-repo",
                123,
                sample_pr_data
            )

        assert result is not None
        assert len(result["failed_checks"]) == 1
        assert result["failed_checks"][0]["conclusion"] == "SKIPPED"

    def test_returns_none_for_all_passing(self, sample_pr_data):
        """Returns None when all checks pass."""
        spec.loader.exec_module(check_module)

        all_passing = {
            "statusCheckRollup": [
                {
                    "name": "ci/test",
                    "conclusion": "SUCCESS",
                    "detailsUrl": "https://github.com/actions/runs/123"
                },
                {
                    "name": "ci/lint",
                    "conclusion": "SUCCESS",
                    "detailsUrl": "https://github.com/actions/runs/124"
                }
            ]
        }

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(all_passing)

        with patch('subprocess.run', return_value=mock_result):
            result = check_module.check_pr_violations(
                "RedHatInsights/test-repo",
                123,
                sample_pr_data
            )

        assert result is None

    def test_handles_gh_cli_error(self, sample_pr_data):
        """Handles gh CLI errors gracefully."""
        spec.loader.exec_module(check_module)

        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch('subprocess.run', return_value=mock_result):
            result = check_module.check_pr_violations(
                "RedHatInsights/test-repo",
                123,
                sample_pr_data
            )

        assert result is None

    def test_handles_timeout(self, sample_pr_data):
        """Handles subprocess timeout gracefully."""
        spec.loader.exec_module(check_module)

        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("gh", 10)):
            result = check_module.check_pr_violations(
                "RedHatInsights/test-repo",
                123,
                sample_pr_data
            )

        assert result is None

    def test_handles_invalid_json(self, sample_pr_data):
        """Handles invalid JSON response gracefully."""
        spec.loader.exec_module(check_module)

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"

        with patch('subprocess.run', return_value=mock_result):
            result = check_module.check_pr_violations(
                "RedHatInsights/test-repo",
                123,
                sample_pr_data
            )

        assert result is None

    def test_includes_pr_metadata(self, sample_pr_data, sample_status_checks):
        """Includes all relevant PR metadata in result."""
        spec.loader.exec_module(check_module)

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(sample_status_checks)

        with patch('subprocess.run', return_value=mock_result):
            result = check_module.check_pr_violations(
                "RedHatInsights/test-repo",
                123,
                sample_pr_data
            )

        assert result["number"] == 123
        assert result["title"] == "Fix critical bug"
        assert result["url"] == "https://github.com/RedHatInsights/test-repo/pull/123"
        assert result["author"] == "developer"
        assert "merged_at" in result


class TestMainFunction:
    """Integration tests for main() function."""

    def test_skips_when_already_scanned_today(self, mock_common_module):
        """Skips scan if already run today."""
        today = datetime.now().strftime("%Y-%m-%d")

        mock_common_module.load_state.return_value = {
            "last_merge_check_scan": today
        }

        spec.loader.exec_module(check_module)
        check_module.main()

        mock_common_module.output_result.assert_called_once()
        call_args = mock_common_module.output_result.call_args[0]
        assert call_args[0] == "skip"
        assert today in call_args[1]

    def test_skips_at_capacity(self, mock_common_module):
        """Skips scan when at capacity."""
        mock_common_module.load_state.return_value = {}
        mock_common_module.get_capacity.return_value = (10, 10)

        spec.loader.exec_module(check_module)
        check_module.main()

        mock_common_module.output_result.assert_called_once()
        call_args = mock_common_module.output_result.call_args[0]
        assert call_args[0] == "skip"
        assert "capacity" in call_args[1].lower()

    def test_skips_when_too_many_violations(self, mock_common_module):
        """Skips when already processing too many violations."""
        mock_common_module.load_state.return_value = {}
        mock_common_module.get_capacity.return_value = (0, 10)

        # Mock 5 active violation tasks
        mock_common_module.get_tasks.return_value = [
            {"external_key": f"merge-violation:repo{i}:123", "status": "in_progress"}
            for i in range(5)
        ]

        spec.loader.exec_module(check_module)
        check_module.main()

        mock_common_module.output_result.assert_called_once()
        call_args = mock_common_module.output_result.call_args[0]
        assert call_args[0] == "skip"
        assert "processing" in call_args[1].lower()

    def test_processes_violations(self, mock_common_module):
        """Processes violations and generates output."""
        mock_common_module.load_state.return_value = {}
        mock_common_module.get_capacity.return_value = (0, 10)
        mock_common_module.get_tasks.return_value = []
        mock_common_module.load_project_repos.return_value = {
            "test-repo": {"upstream": "https://github.com/RedHatInsights/test-repo"}
        }
        mock_common_module.upstream_repo.return_value = (
            "RedHatInsights/test-repo", "github"
        )

        # Mock gh pr list response (recent PR with timezone-aware timestamp)
        from datetime import timezone
        recent_pr = {
            "number": 123,
            "title": "Fix critical bug",
            "url": "https://github.com/RedHatInsights/test-repo/pull/123",
            "author": {"login": "developer"},
            "mergedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        pr_list_response = [recent_pr]

        # Mock gh pr view response with violations
        pr_view_response = {
            "statusCheckRollup": [
                {
                    "name": "ci/test",
                    "conclusion": "FAILURE",
                    "detailsUrl": "https://github.com/actions/runs/123"
                }
            ]
        }

        def mock_subprocess_run(cmd, **kwargs):
            result = Mock()
            result.returncode = 0

            if "list" in cmd:
                result.stdout = json.dumps(pr_list_response)
            elif "view" in cmd:
                result.stdout = json.dumps(pr_view_response)

            return result

        spec.loader.exec_module(check_module)

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            check_module.main()

        # Verify output was called with violations
        mock_common_module.output_result.assert_called_once()
        call_args = mock_common_module.output_result.call_args[0]
        assert call_args[0] == "start"
        assert "violation" in call_args[1].lower()

        # Verify state was saved
        mock_common_module.save_state.assert_called_once()

    def test_skips_non_github_repos(self, mock_common_module):
        """Skips repositories not hosted on GitHub."""
        mock_common_module.load_state.return_value = {}
        mock_common_module.get_capacity.return_value = (0, 10)
        mock_common_module.load_project_repos.return_value = {
            "gitlab-repo": {"upstream": "https://gitlab.com/test/repo"}
        }
        mock_common_module.upstream_repo.return_value = (
            "test/repo", "gitlab"  # Non-GitHub host
        )

        spec.loader.exec_module(check_module)
        check_module.main()

        # Should skip and output "no violations"
        mock_common_module.output_result.assert_called_once()
        call_args = mock_common_module.output_result.call_args[0]
        assert call_args[0] == "skip"

    def test_filters_by_24h_window(self, mock_common_module):
        """Only processes PRs merged in last 24 hours."""
        from datetime import timezone
        mock_common_module.load_state.return_value = {}
        mock_common_module.get_capacity.return_value = (0, 10)
        mock_common_module.load_project_repos.return_value = {
            "test-repo": {"upstream": "https://github.com/RedHatInsights/test-repo"}
        }
        mock_common_module.upstream_repo.return_value = (
            "RedHatInsights/test-repo", "github"
        )

        # Create PRs: one recent, one old (both timezone-aware)
        recent_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat().replace("+00:00", "Z")

        pr_list_response = [
            {
                "number": 123,
                "title": "Recent PR",
                "url": "https://github.com/test/pull/123",
                "author": {"login": "dev"},
                "mergedAt": recent_time
            },
            {
                "number": 122,
                "title": "Old PR",
                "url": "https://github.com/test/pull/122",
                "author": {"login": "dev"},
                "mergedAt": old_time
            }
        ]

        violations_response = {
            "statusCheckRollup": [
                {"name": "test", "conclusion": "FAILURE", "detailsUrl": "url"}
            ]
        }

        call_count = 0

        def mock_subprocess_run(cmd, **kwargs):
            nonlocal call_count
            result = Mock()
            result.returncode = 0

            if "list" in cmd:
                result.stdout = json.dumps(pr_list_response)
            elif "view" in cmd:
                call_count += 1
                result.stdout = json.dumps(violations_response)

            return result

        spec.loader.exec_module(check_module)

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            check_module.main()

        # Should only check the recent PR (within 24h window)
        assert call_count == 1


class TestSeverityAssessment:
    """Tests for severity assessment in violation output."""

    def test_failure_is_high_severity(self, mock_common_module):
        """FAILURE conclusions are marked as HIGH severity."""
        from datetime import timezone
        mock_common_module.load_state.return_value = {}
        mock_common_module.get_capacity.return_value = (0, 10)
        mock_common_module.load_project_repos.return_value = {
            "test-repo": {"upstream": "https://github.com/RedHatInsights/test-repo"}
        }
        mock_common_module.upstream_repo.return_value = (
            "RedHatInsights/test-repo", "github"
        )

        recent_pr = {
            "number": 123,
            "title": "Fix critical bug",
            "url": "https://github.com/RedHatInsights/test-repo/pull/123",
            "author": {"login": "developer"},
            "mergedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        pr_list_response = [recent_pr]
        pr_view_response = {
            "statusCheckRollup": [
                {"name": "test", "conclusion": "FAILURE", "detailsUrl": "url"}
            ]
        }

        def mock_subprocess_run(cmd, **kwargs):
            result = Mock()
            result.returncode = 0

            if "list" in cmd:
                result.stdout = json.dumps(pr_list_response)
            elif "view" in cmd:
                result.stdout = json.dumps(pr_view_response)

            return result

        spec.loader.exec_module(check_module)

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            check_module.main()

        call_args = mock_common_module.output_result.call_args[0]
        assert "HIGH" in call_args[1]

    def test_cancelled_is_medium_severity(self, mock_common_module):
        """CANCELLED conclusions are marked as MEDIUM severity."""
        from datetime import timezone
        mock_common_module.load_state.return_value = {}
        mock_common_module.get_capacity.return_value = (0, 10)
        mock_common_module.load_project_repos.return_value = {
            "test-repo": {"upstream": "https://github.com/RedHatInsights/test-repo"}
        }
        mock_common_module.upstream_repo.return_value = (
            "RedHatInsights/test-repo", "github"
        )

        recent_pr = {
            "number": 123,
            "title": "Fix critical bug",
            "url": "https://github.com/RedHatInsights/test-repo/pull/123",
            "author": {"login": "developer"},
            "mergedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        pr_list_response = [recent_pr]
        pr_view_response = {
            "statusCheckRollup": [
                {"name": "test", "conclusion": "CANCELLED", "detailsUrl": "url"}
            ]
        }

        def mock_subprocess_run(cmd, **kwargs):
            result = Mock()
            result.returncode = 0

            if "list" in cmd:
                result.stdout = json.dumps(pr_list_response)
            elif "view" in cmd:
                result.stdout = json.dumps(pr_view_response)

            return result

        spec.loader.exec_module(check_module)

        with patch('subprocess.run', side_effect=mock_subprocess_run):
            check_module.main()

        call_args = mock_common_module.output_result.call_args[0]
        assert "MEDIUM" in call_args[1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
