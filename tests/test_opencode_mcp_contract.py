"""Pin HCC profile MCP preparation to the native OpenCode render contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEV_BOT_ROOT = REPOSITORY_ROOT / "dev-bot"
sys.path.insert(0, str(DEV_BOT_ROOT))

from bot.config import discover_optional_mcp_servers, load_mcp_servers  # noqa: E402
from bot.merge import MergeReport, merge_mcp_servers  # noqa: E402


def test_framework_mcp_preparation_feeds_conflict_free_native_renderer_input(
    tmp_path: Path,
) -> None:
    """Profile and project MCP inputs must both reach the V2 renderer once."""
    profile = REPOSITORY_ROOT / "instance/framework-config/agent"
    dev_bot = DEV_BOT_ROOT
    profile_mcp = json.loads((profile / "mcp.json").read_text())
    built_in_mcp = json.loads((dev_bot / "bot/mcp.json").read_text())
    merged_mcp = merge_mcp_servers(built_in_mcp, profile_mcp, MergeReport())

    (tmp_path / "bot").mkdir()
    (tmp_path / "bot/mcp.json").write_text(json.dumps(built_in_mcp))
    (tmp_path / "data").mkdir()
    (tmp_path / "data/merged-mcp.json").write_text(json.dumps(merged_mcp))
    (tmp_path / ".mcp.json").write_text((dev_bot / ".mcp.json").read_text())

    active_envs = yaml.safe_load((profile / "instance.yaml").read_text())["envs"]
    for env_name in active_envs:
        source = dev_bot / "presets/envs" / env_name / "manifest.yaml"
        if source.is_file():
            destination = tmp_path / "presets/envs" / env_name / "manifest.yaml"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(source.read_text())

    prepared_servers = load_mcp_servers(
        tmp_path,
        resolve_env=False,
        include_project=True,
    )
    optional_servers = discover_optional_mcp_servers(tmp_path)

    assert prepared_servers["hcc-patternfly-data-view"] == {
        "command": "hcc-pf-mcp",
        "args": [],
    }
    assert (
        prepared_servers["chrome-devtools"]
        == json.loads((dev_bot / ".mcp.json").read_text())["mcpServers"][
            "chrome-devtools"
        ]
    )
    assert {"hcc-patternfly-data-view", "chrome-devtools"}.issubset(optional_servers)

    # The renderer gets prepared_servers as openCodeMcpServers. Profile-native
    # MCP additions must not redefine these generated servers.
    profile_config = json.loads((profile / "opencode.json").read_text())
    profile_servers = profile_config.get("mcp", {}).get("servers", {})
    assert not set(prepared_servers).intersection(profile_servers)
    assert "chrome-devtools" in prepared_servers
    assert "hcc-patternfly-data-view" in prepared_servers
