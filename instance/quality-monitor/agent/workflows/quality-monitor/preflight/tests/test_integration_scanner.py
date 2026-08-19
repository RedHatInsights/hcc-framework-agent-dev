#!/usr/bin/env python3
"""Integration tests for anti-pattern scanner using test fixtures."""

import pytest
import yaml
from pathlib import Path
from unittest.mock import Mock
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# Mock common module BEFORE any imports
mock_common = Mock()
sys.modules["common"] = mock_common

# Import after mocking common
import importlib

spec = importlib.util.spec_from_file_location(
    "scan_anti_patterns", Path(__file__).parent.parent / "02-scan-test-anti-patterns.py"
)
scan_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan_module)


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def good_repo(fixtures_dir):
    """Path to repository with good test practices."""
    return fixtures_dir / "good-repo"


@pytest.fixture
def bad_repo(fixtures_dir):
    """Path to repository with anti-patterns."""
    return fixtures_dir / "bad-repo"


@pytest.fixture
def anti_patterns():
    """Load anti-patterns.yaml for validation."""
    patterns_file = Path(__file__).parent.parent.parent / "anti-patterns.yaml"
    with open(patterns_file) as f:
        return yaml.safe_load(f)


class TestGoodRepoIntegration:
    """Integration tests against fixture repo with good practices."""

    def test_detects_playwright_framework(self, good_repo):
        """Should detect Playwright via config file."""
        config = scan_module.load_config()
        framework = scan_module.detect_framework(good_repo, config)

        assert framework == "playwright"

    def test_finds_test_files(self, good_repo):
        """Should find .spec.ts test files."""
        config = scan_module.load_config()

        # Generate file list from fixture directory (simulates API response)
        file_list = [
            str(p.relative_to(good_repo)) for p in good_repo.rglob("*") if p.is_file()
        ]

        test_files = scan_module.find_test_files_from_list(
            file_list, "good-repo", config, max_files=20
        )

        assert len(test_files) == 1
        assert test_files[0]["path"] == "login.spec.ts"

    def test_good_repo_has_no_hard_coded_sleeps(self, good_repo):
        """Good repo should not have waitForTimeout or setTimeout in tests."""
        test_file = good_repo / "login.spec.ts"
        content = test_file.read_text()

        # Should NOT contain anti-patterns
        assert "waitForTimeout" not in content
        assert "setTimeout" not in content
        assert "test.skip" not in content

    def test_good_repo_has_assertions(self, good_repo):
        """Good repo should have proper assertions."""
        test_file = good_repo / "login.spec.ts"
        content = test_file.read_text()

        # Should contain proper waits and assertions
        assert "expect(" in content
        assert "toBeVisible" in content
        assert "waitForSelector" in content or "waitForResponse" in content

    def test_good_repo_uses_auth_package(self, good_repo):
        """Good repo should import from playwright-test-auth, not @playwright/test."""
        test_file = good_repo / "login.spec.ts"
        content = test_file.read_text()

        assert "@redhat-cloud-services/playwright-test-auth" in content
        assert "from '@playwright/test'" not in content


class TestBadRepoIntegration:
    """Integration tests against fixture repo with anti-patterns."""

    def test_detects_playwright_framework(self, bad_repo):
        """Should detect Playwright via config file."""
        config = scan_module.load_config()
        framework = scan_module.detect_framework(bad_repo, config)

        assert framework == "playwright"

    def test_finds_test_files(self, bad_repo):
        """Should find .spec.ts test files."""
        config = scan_module.load_config()

        # Generate file list from fixture directory (simulates API response)
        file_list = [
            str(p.relative_to(bad_repo)) for p in bad_repo.rglob("*") if p.is_file()
        ]

        test_files = scan_module.find_test_files_from_list(
            file_list, "bad-repo", config, max_files=20
        )

        assert len(test_files) == 1
        assert test_files[0]["path"] == "checkout.spec.ts"

    def test_bad_repo_has_hard_coded_sleeps(self, bad_repo, anti_patterns):
        """Bad repo should contain hard-coded sleep patterns."""
        test_file = bad_repo / "checkout.spec.ts"
        content = test_file.read_text()

        # Should contain the anti-patterns we're looking for
        assert "waitForTimeout" in content
        assert "setTimeout" in content

        # Verify these match our anti-patterns.yaml definitions
        hard_coded_sleep = anti_patterns["anti_patterns"]["hard_coded_sleep"]
        assert hard_coded_sleep["severity"] == "high"

    def test_bad_repo_has_disabled_tests(self, bad_repo, anti_patterns):
        """Bad repo should contain disabled tests."""
        test_file = bad_repo / "checkout.spec.ts"
        content = test_file.read_text()

        # Should contain disabled tests
        assert "test.skip" in content

        # Verify these match our anti-patterns.yaml definitions
        disabled_test = anti_patterns["anti_patterns"]["disabled_tests"]
        assert disabled_test["severity"] == "medium"

    def test_bad_repo_has_missing_assertions(self, bad_repo, anti_patterns):
        """Bad repo should contain tests with missing assertions."""
        test_file = bad_repo / "checkout.spec.ts"
        content = test_file.read_text()

        # File should have tests that are missing assertions
        # (We look for the comment marker to identify these)
        assert (
            "ANTI-PATTERN: No assertion" in content
            or "ANTI-PATTERN: Missing assertion" in content
        )

        # Verify pattern is defined
        missing_assertion = anti_patterns["anti_patterns"]["missing_assertions"]
        assert missing_assertion["severity"] == "high"

    def test_bad_repo_missing_auth_package(self, bad_repo, anti_patterns):
        """Bad repo should import from @playwright/test instead of playwright-test-auth."""
        test_file = bad_repo / "checkout.spec.ts"
        content = test_file.read_text()

        assert "from '@playwright/test'" in content
        assert "@redhat-cloud-services/playwright-test-auth" not in content

        missing_auth = anti_patterns["anti_patterns"]["missing_auth_package"]
        assert missing_auth["severity"] == "high"

    def test_bad_repo_examples_match_anti_patterns(self, bad_repo, anti_patterns):
        """Verify that bad examples in fixtures match anti-patterns.yaml examples."""
        test_file = bad_repo / "checkout.spec.ts"
        content = test_file.read_text()

        # Check hard-coded sleep pattern
        hard_coded_pattern = anti_patterns["anti_patterns"]["hard_coded_sleep"]
        bad_example = hard_coded_pattern["examples"]["bad"]

        # Our fixture should contain similar patterns to the examples
        if "waitForTimeout" in bad_example:
            assert "waitForTimeout" in content
        if "setTimeout" in bad_example:
            assert "setTimeout" in content


class TestAntiPatternsConfiguration:
    """Validate that anti-patterns.yaml is properly structured."""

    def test_anti_patterns_file_exists(self):
        """anti-patterns.yaml must exist."""
        patterns_file = Path(__file__).parent.parent.parent / "anti-patterns.yaml"
        assert patterns_file.exists()

    def test_anti_patterns_has_required_structure(self, anti_patterns):
        """anti-patterns.yaml must have required structure."""
        assert "anti_patterns" in anti_patterns
        assert isinstance(anti_patterns["anti_patterns"], dict)

    def test_high_severity_patterns_defined(self, anti_patterns):
        """High severity patterns must be defined."""
        patterns = anti_patterns["anti_patterns"]

        # These are the critical patterns we scan for
        high_severity = [
            "hard_coded_sleep",
            "missing_assertions",
            "missing_auth_package",
        ]

        for pattern_key in high_severity:
            assert pattern_key in patterns, (
                f"Missing high severity pattern: {pattern_key}"
            )
            pattern = patterns[pattern_key]
            assert pattern["severity"] == "high"
            assert "message" in pattern
            assert "recommendation" in pattern
            assert "examples" in pattern

    def test_examples_have_bad_and_good(self, anti_patterns):
        """Each pattern should have bad and good examples."""
        for pattern_name, pattern in anti_patterns["anti_patterns"].items():
            if "examples" in pattern:
                examples = pattern["examples"]
                # Should have at least 'bad' example, 'good' is recommended
                assert "bad" in examples, (
                    f"Pattern {pattern_name} missing 'bad' example"
                )


class TestScannerEndToEnd:
    """End-to-end integration test simulating real workflow."""

    def test_good_repo_would_not_trigger_workflow(self, good_repo):
        """Scanner should not flag good repo as needing attention."""
        config = scan_module.load_config()

        # Detect framework
        framework = scan_module.detect_framework(good_repo, config)
        assert framework == "playwright"

        # Find test files (simulating API response)
        file_list = [
            str(p.relative_to(good_repo)) for p in good_repo.rglob("*") if p.is_file()
        ]
        test_files = scan_module.find_test_files_from_list(
            file_list, "good-repo", config, max_files=20
        )
        assert len(test_files) > 0

        # Read test file content
        test_file = good_repo / test_files[0]["path"]
        content = test_file.read_text()

        # Verify no obvious anti-patterns present
        assert "waitForTimeout" not in content
        assert "setTimeout" not in content
        assert "test.skip" not in content

    def test_bad_repo_would_trigger_workflow(self, bad_repo):
        """Scanner should flag bad repo for AI analysis."""
        config = scan_module.load_config()

        # Detect framework
        framework = scan_module.detect_framework(bad_repo, config)
        assert framework == "playwright"

        # Find test files (simulating API response)
        file_list = [
            str(p.relative_to(bad_repo)) for p in bad_repo.rglob("*") if p.is_file()
        ]
        test_files = scan_module.find_test_files_from_list(
            file_list, "bad-repo", config, max_files=20
        )
        assert len(test_files) > 0

        # Read test file content
        test_file = bad_repo / test_files[0]["path"]
        content = test_file.read_text()

        # Should have multiple anti-patterns
        anti_pattern_count = 0

        if "waitForTimeout" in content:
            anti_pattern_count += 1

        if "setTimeout" in content:
            anti_pattern_count += 1

        if "test.skip" in content:
            anti_pattern_count += 1

        # Bad repo should trigger at least 2 different anti-patterns
        assert anti_pattern_count >= 2, (
            f"Expected multiple anti-patterns, found {anti_pattern_count}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
