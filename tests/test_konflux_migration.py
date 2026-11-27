"""Replay release regressions from widget-layout without live cluster access."""

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PROFILE = Path(__file__).resolve().parents[1] / "instance/framework-config/agent"
SKILL = PROFILE / ".opencode/skills/konflux-migration"


def test_config_agent_references_discoverable_migration_skill():
    metadata = yaml.safe_load((SKILL / "SKILL.md").read_text().split("---", 2)[1])
    assert metadata["name"] == SKILL.name
    assert metadata["description"]
    config_agent = (PROFILE / ".opencode/agents/config.md").read_text()
    assert f"`{SKILL.name}`" in config_agent


def manifest(url, policy, visibility):
    component = {"name": "widget", "repositories": [{"url": url, "tags": ["latest"]}]}
    if visibility is not None:
        component["public"] = visibility
    return {
        "kind": "ReleasePlanAdmission",
        "spec": {
            "policy": policy,
            "data": {"mapping": {"components": [{"name": "other"}, component]}},
        },
    }


@pytest.mark.parametrize(
    "before,after,policy,expected",
    [
        (True, None, "frontend", "public"),
        (True, True, "backend", "policy"),
        (False, False, "frontend", ""),
        (False, True, "frontend", "public"),
    ],
)
def test_release_behavior(tmp_path, before, after, policy, expected):
    src, dst = tmp_path / "source.yaml", tmp_path / "destination.yaml"
    src.write_text(yaml.safe_dump(manifest("old/widget", "frontend", before)))
    dst.write_text(yaml.safe_dump(manifest("new/widget", policy, after)))
    result = subprocess.run(
        [
            sys.executable,
            SKILL / "check_rpa.py",
            src,
            dst,
            "widget",
            "old/widget",
            "new/widget",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == int(bool(expected)), result.stderr
    assert result.stdout.partition(":")[0] == expected
