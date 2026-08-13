#!/usr/bin/env python3
"""Tests for 00-cycle-sleep.py preflight script."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
import importlib

spec = importlib.util.spec_from_file_location(
    "cycle_sleep", Path(__file__).parent.parent / "00-cycle-sleep.py"
)
cycle_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cycle_module)


class TestCycleSleep:
    """Tests for the cycle-sleep preflight script."""

    def test_writes_cycle_sleep_file(self, tmp_path):
        """Writes cycle-sleep.json with 24-hour sleep duration."""
        sleep_file = tmp_path / "data" / "cycle-sleep.json"

        with patch.object(cycle_module, "CYCLE_SLEEP_FILE", sleep_file):
            cycle_module.main()

        assert sleep_file.exists()
        data = json.loads(sleep_file.read_text())
        assert data["recommended_sleep"] == 86400
        assert "reason" in data

    def test_outputs_skip_status(self, tmp_path, capsys):
        """Outputs skip status with cycle-sleep message."""
        sleep_file = tmp_path / "data" / "cycle-sleep.json"

        with patch.object(cycle_module, "CYCLE_SLEEP_FILE", sleep_file):
            cycle_module.main()

        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["status"] == "skip"
        assert "86400" in result["content"]

    def test_creates_data_directory(self, tmp_path):
        """Creates the data directory if it doesn't exist."""
        sleep_file = tmp_path / "nested" / "data" / "cycle-sleep.json"

        with patch.object(cycle_module, "CYCLE_SLEEP_FILE", sleep_file):
            cycle_module.main()

        assert sleep_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
