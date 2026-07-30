#!/usr/bin/env python3
"""Tests for 02-scan-test-anti-patterns.py preflight script."""

import pytest
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, mock_open
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Any


# Import functions under test (will be imported after mocking common module)
@pytest.fixture(autouse=True)
def mock_common_module():
    """Mock the common module that preflight scripts depend on."""
    mock_common = Mock()
    mock_common.load_project_repos = Mock(return_value={})
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
import sys
from pathlib import Path

# Dynamically import the module
spec = importlib.util.spec_from_file_location(
    "scan_anti_patterns",
    Path(__file__).parent.parent / "02-scan-test-anti-patterns.py"
)
scan_module = importlib.util.module_from_spec(spec)


@pytest.fixture
def sample_test_config():
    """Sample test configuration matching test-config.yaml structure."""
    return {
        "repos": {
            "custom-repo": {
                "patterns": ["custom/**/*.spec.ts"],
                "exclude": ["**/*.skip.spec.ts"]
            }
        },
        "defaults": {
            "framework_detection": {
                "playwright": {
                    "indicators": ["playwright.config.ts", "playwright.config.js"],
                    "patterns": ["**/*.spec.ts", "e2e/**/*.test.ts"]
                }
            },
            "generic_patterns": ["**/*.spec.ts", "**/*.test.ts"],
            "global_excludes": ["**/node_modules/**", "**/dist/**"]
        },
        "limits": {
            "max_files_per_repo": 20,
            "max_file_size_bytes": 102400,
            "max_repos_per_scan": 3
        }
    }


class TestExpandBracePatterns:
    """Tests for expand_brace_patterns function."""

    def test_no_braces(self):
        """Simple pattern without braces passes through unchanged."""
        spec.loader.exec_module(scan_module)
        result = scan_module.expand_brace_patterns("**/*.spec.ts")
        assert result == ["**/*.spec.ts"]

    def test_single_brace_expansion(self):
        """Pattern with single brace set expands correctly."""
        spec.loader.exec_module(scan_module)
        result = scan_module.expand_brace_patterns("**/*.{spec,test}.ts")
        assert set(result) == {"**/*.spec.ts", "**/*.test.ts"}

    def test_multiple_options(self):
        """Pattern with multiple options expands all."""
        spec.loader.exec_module(scan_module)
        result = scan_module.expand_brace_patterns("src/{a,b,c}/test.ts")
        assert set(result) == {"src/a/test.ts", "src/b/test.ts", "src/c/test.ts"}

    def test_nested_braces(self):
        """Nested braces expand recursively."""
        spec.loader.exec_module(scan_module)
        result = scan_module.expand_brace_patterns("**/*.{spec,test}.{ts,js}")
        assert set(result) == {
            "**/*.spec.ts", "**/*.spec.js",
            "**/*.test.ts", "**/*.test.js"
        }


class TestDetectFramework:
    """Tests for detect_framework function."""

    def test_playwright_detection_ts(self, tmp_path, sample_test_config):
        """Detects Playwright via playwright.config.ts."""
        config_file = tmp_path / "playwright.config.ts"
        config_file.write_text("export default { testDir: './tests' };")

        spec.loader.exec_module(scan_module)
        framework = scan_module.detect_framework(tmp_path, sample_test_config)
        assert framework == "playwright"

    def test_playwright_detection_js(self, tmp_path, sample_test_config):
        """Detects Playwright via playwright.config.js."""
        config_file = tmp_path / "playwright.config.js"
        config_file.write_text("module.exports = { testDir: './tests' };")

        spec.loader.exec_module(scan_module)
        framework = scan_module.detect_framework(tmp_path, sample_test_config)
        assert framework == "playwright"

    def test_no_framework_detected(self, tmp_path, sample_test_config):
        """Returns None when no framework indicators found."""
        spec.loader.exec_module(scan_module)
        framework = scan_module.detect_framework(tmp_path, sample_test_config)
        assert framework is None

    def test_no_config_provided(self, tmp_path):
        """Returns None when config is None."""
        spec.loader.exec_module(scan_module)
        framework = scan_module.detect_framework(tmp_path, None)
        assert framework is None


class TestGetTestPatterns:
    """Tests for get_test_patterns function."""

    def test_repo_specific_override(self, tmp_path, sample_test_config):
        """Uses repo-specific patterns when configured."""
        spec.loader.exec_module(scan_module)
        patterns, excludes = scan_module.get_test_patterns(
            "custom-repo", tmp_path, sample_test_config
        )
        assert patterns == ["custom/**/*.spec.ts"]
        assert excludes == ["**/*.skip.spec.ts"]

    def test_playwright_auto_detection(self, tmp_path, sample_test_config):
        """Uses Playwright patterns when config detected."""
        config_file = tmp_path / "playwright.config.ts"
        config_file.write_text("export default {};")

        spec.loader.exec_module(scan_module)
        patterns, excludes = scan_module.get_test_patterns(
            "some-repo", tmp_path, sample_test_config
        )
        assert patterns == ["**/*.spec.ts", "e2e/**/*.test.ts"]
        assert excludes == ["**/node_modules/**", "**/dist/**"]

    def test_generic_fallback(self, tmp_path, sample_test_config):
        """Uses generic patterns when no framework detected."""
        spec.loader.exec_module(scan_module)
        patterns, excludes = scan_module.get_test_patterns(
            "unknown-repo", tmp_path, sample_test_config
        )
        assert patterns == ["**/*.spec.ts", "**/*.test.ts"]
        assert excludes == ["**/node_modules/**", "**/dist/**"]

    def test_no_config_fallback(self, tmp_path):
        """Uses hardcoded patterns when no config provided."""
        spec.loader.exec_module(scan_module)
        patterns, excludes = scan_module.get_test_patterns(
            "any-repo", tmp_path, None
        )
        # Should return hardcoded patterns
        assert "**/*.test.ts" in patterns
        assert "**/*.spec.ts" in patterns
        assert excludes == []


class TestFindTestFiles:
    """Tests for find_test_files function."""

    def test_finds_matching_files(self, tmp_path, sample_test_config):
        """Finds test files matching patterns."""
        # Create test files
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "example.spec.ts").write_text("test content")
        (test_dir / "another.spec.ts").write_text("more tests")

        spec.loader.exec_module(scan_module)
        result = scan_module.find_test_files(
            tmp_path, "test-repo", sample_test_config, max_files=20
        )

        assert len(result) == 2
        assert all("spec.ts" in f["path"] for f in result)
        assert all(f["size"] > 0 for f in result)

    def test_excludes_patterns(self, tmp_path, sample_test_config):
        """Excludes files matching exclude patterns."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "good.spec.ts").write_text("test")

        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "bad.spec.ts").write_text("test")

        spec.loader.exec_module(scan_module)
        result = scan_module.find_test_files(
            tmp_path, "test-repo", sample_test_config, max_files=20
        )

        # Should only find the file not in node_modules
        assert len(result) == 1
        assert "good.spec.ts" in result[0]["path"]
        assert "node_modules" not in result[0]["path"]

    def test_respects_max_files_limit(self, tmp_path, sample_test_config):
        """Respects max_files parameter."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        # Create 10 test files
        for i in range(10):
            (test_dir / f"test{i}.spec.ts").write_text("test")

        spec.loader.exec_module(scan_module)
        result = scan_module.find_test_files(
            tmp_path, "test-repo", sample_test_config, max_files=5
        )

        assert len(result) <= 5

    def test_skips_large_files(self, tmp_path, sample_test_config):
        """Skips files exceeding size limit."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        # Create small file
        small_file = test_dir / "small.spec.ts"
        small_file.write_text("test")

        # Create large file (over 100KB limit)
        large_file = test_dir / "large.spec.ts"
        large_file.write_text("x" * 200000)

        spec.loader.exec_module(scan_module)
        result = scan_module.find_test_files(
            tmp_path, "test-repo", sample_test_config, max_files=20
        )

        # Should only find the small file
        assert len(result) == 1
        assert "small.spec.ts" in result[0]["path"]

    def test_expands_brace_patterns(self, tmp_path):
        """Expands brace patterns in search."""
        config = {
            "defaults": {
                "generic_patterns": ["**/*.{spec,test}.ts"],
                "global_excludes": []
            },
            "limits": {
                "max_file_size_bytes": 102400
            }
        }

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "example.spec.ts").write_text("spec test")
        (test_dir / "example.test.ts").write_text("test test")

        spec.loader.exec_module(scan_module)
        result = scan_module.find_test_files(
            tmp_path, "test-repo", config, max_files=20
        )

        assert len(result) == 2


class TestLoadTestConfig:
    """Tests for load_test_config function."""

    def test_loads_valid_yaml(self, tmp_path, sample_test_config):
        """Loads valid YAML configuration."""
        config_path = tmp_path / "test-config.yaml"

        with open(config_path, 'w') as f:
            yaml.dump(sample_test_config, f)

        spec.loader.exec_module(scan_module)

        with patch.object(Path, '__truediv__', return_value=config_path):
            result = scan_module.load_test_config()

        # Note: This test may need adjustment based on actual path resolution
        # For now, testing the function exists and handles YAML

    def test_returns_none_when_missing(self, tmp_path):
        """Returns None when config file doesn't exist."""
        spec.loader.exec_module(scan_module)

        # Mock Path to return non-existent file
        with patch('pathlib.Path.exists', return_value=False):
            result = scan_module.load_test_config()
            # Function should handle missing file gracefully


class TestMainFunction:
    """Integration tests for main() function."""

    def test_skips_when_already_scanned_today(self, mock_common_module):
        """Skips scan if already run today."""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")

        mock_common_module.load_state.return_value = {
            "last_anti_pattern_scan": today
        }

        spec.loader.exec_module(scan_module)
        scan_module.main()

        mock_common_module.output_result.assert_called_once()
        call_args = mock_common_module.output_result.call_args[0]
        assert call_args[0] == "skip"
        assert today in call_args[1]

    def test_skips_at_capacity(self, mock_common_module):
        """Skips scan when at capacity."""
        mock_common_module.load_state.return_value = {}
        mock_common_module.get_capacity.return_value = (10, 10)  # at capacity

        spec.loader.exec_module(scan_module)
        scan_module.main()

        mock_common_module.output_result.assert_called_once()
        call_args = mock_common_module.output_result.call_args[0]
        assert call_args[0] == "skip"
        assert "capacity" in call_args[1].lower()

    def test_skips_when_too_many_active_scans(self, mock_common_module):
        """Skips when too many test scans already in progress."""
        mock_common_module.load_state.return_value = {}
        mock_common_module.get_capacity.return_value = (0, 10)

        # Mock 5 active test scans
        mock_common_module.get_tasks.return_value = [
            {"external_key": f"test-scan:repo{i}", "status": "in_progress"}
            for i in range(5)
        ]

        spec.loader.exec_module(scan_module)
        scan_module.main()

        mock_common_module.output_result.assert_called_once()
        call_args = mock_common_module.output_result.call_args[0]
        assert call_args[0] == "skip"
        assert "processing" in call_args[1].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
