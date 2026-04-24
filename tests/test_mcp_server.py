"""Tests for the MCP server tool registration and basic behaviour."""

from __future__ import annotations

import pytest

from saturnzap import mcp_server


@pytest.fixture(autouse=True)
def _clean_data_dir(tmp_path, monkeypatch):
    """Point data dir to a temp directory so no seed/node state leaks."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


# ---------------------------------------------------------------------------
# Server instantiation
# ---------------------------------------------------------------------------


def test_mcp_server_is_fastmcp():
    """The exported mcp object is a FastMCP instance."""
    from mcp.server.fastmcp import FastMCP

    assert isinstance(mcp_server.mcp, FastMCP)


def test_server_name():
    assert mcp_server.mcp.name == "saturnzap"


# ---------------------------------------------------------------------------
# Tool registration — verify all 23 tools are present
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = [
    "is_initialized",
    "init_wallet",
    "setup_wallet",
    "get_status",
    "get_connect_info",
    "stop_node",
    "new_onchain_address",
    "get_balance",
    "send_onchain",
    "connect_peer",
    "disconnect_peer",
    "list_peers",
    "list_channels",
    "open_channel",
    "close_channel",
    "create_invoice",
    "pay_invoice",
    "keysend",
    "list_transactions",
    "l402_fetch",
    "liquidity_status",
    "request_inbound",
    "list_lqwd_nodes",
    "backup_wallet",
    "restore_wallet",
]


def test_all_tools_registered():
    """Every planned tool is registered on the FastMCP server."""
    registered = set(mcp_server.mcp._tool_manager._tools.keys())
    for name in EXPECTED_TOOLS:
        assert name in registered, f"Tool '{name}' not registered"


def test_tool_count():
    """Exactly the expected number of tools are registered."""
    registered = mcp_server.mcp._tool_manager._tools
    assert len(registered) == len(EXPECTED_TOOLS)


# ---------------------------------------------------------------------------
# Tool functions — unit-level tests (no LDK node needed)
# ---------------------------------------------------------------------------


def test_is_initialized_returns_false(tmp_path, monkeypatch):
    """is_initialized returns False when no seed exists."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    result = mcp_server.is_initialized()
    assert result == {"initialized": False}


def test_init_wallet_when_already_initialized(tmp_path, monkeypatch):
    """init_wallet returns error dict when seed already exists."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    # Create a fake seed file to simulate initialization
    from saturnzap.config import data_dir

    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "seed.enc").write_text("fake")
    (d / "seed.salt").write_bytes(b"0" * 16)

    result = mcp_server.init_wallet()
    assert result["status"] == "error"
    assert result["code"] == "ALREADY_INITIALIZED"


def test_list_lqwd_nodes():
    """list_lqwd_nodes returns all nodes when no region filter."""
    result = mcp_server.list_lqwd_nodes()
    assert "nodes" in result
    assert "count" in result
    assert result["count"] == len(result["nodes"])
    assert result["count"] > 0


def test_list_lqwd_nodes_filtered():
    """list_lqwd_nodes filters by region."""
    result = mcp_server.list_lqwd_nodes(region="CA")
    assert result["count"] == 1
    assert result["nodes"][0]["region"] == "CA"


def test_list_lqwd_nodes_unknown_region():
    """list_lqwd_nodes returns empty for unknown region."""
    result = mcp_server.list_lqwd_nodes(region="XX")
    assert result["count"] == 0
    assert result["nodes"] == []


# ---------------------------------------------------------------------------
# serve entry point exists
# ---------------------------------------------------------------------------


def test_serve_is_callable():
    assert callable(mcp_server.serve)


# ---------------------------------------------------------------------------
# CLI `mcp` subcommand registered
# ---------------------------------------------------------------------------


def test_cli_mcp_help():
    """The 'mcp' subcommand appears in CLI help."""
    from typer.testing import CliRunner

    from saturnzap.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "mcp" in result.output


# ── Additional tool-level tests ──────────────────────────────────


def test_setup_wallet_when_already_init(tmp_path, monkeypatch):
    """setup_wallet should skip init step when already initialized."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("SZ_PASSPHRASE", "pw")
    from saturnzap import keystore

    keystore.save_encrypted("abandon " * 23 + "art", "pw")

    from unittest.mock import MagicMock, patch
    mock_node = MagicMock()
    mock_node.node_id.return_value = "02abc"
    mock_node.onchain_payment.return_value.new_address.return_value = "tb1q"
    mock_node.list_balances.return_value = MagicMock(
        total_onchain_balance_sats=0,
        spendable_onchain_balance_sats=0,
        total_lightning_balance_sats=0,
        total_anchor_channels_reserve_sats=0,
    )
    mock_node.list_channels.return_value = []

    with patch("saturnzap.node.start", return_value=mock_node):
        result = mcp_server.setup_wallet(auto=False)

    assert result["status"] == "ok"
    init_step = next(s for s in result["steps"] if s["step"] == "init")
    assert init_step["skipped"] is True


def test_tool_names_snake_case():
    """All registered tool names should be snake_case."""
    import re
    registered = mcp_server.mcp._tool_manager._tools.keys()
    for name in registered:
        assert re.match(r'^[a-z][a-z0-9_]*$', name), f"Tool '{name}' not snake_case"


def test_open_channel_tool_tri_state_announce():
    """open_channel tool with announce=None invokes the auto gate."""
    from unittest.mock import patch

    decision = {"announce": False, "reason": "unreachable", "warnings": ["hint"]}
    with (
        patch("saturnzap.node.decide_announce", return_value=decision) as gate,
        patch("saturnzap.node.open_channel", return_value="ucid_z"),
    ):
        result = mcp_server.open_channel("02pk", "1.2.3.4:9735", 100_000)

    assert result["status"] == "ok"
    assert result["user_channel_id"] == "ucid_z"
    assert result["announce"] is False
    assert result["announce_reason"] == "unreachable"
    assert result["warnings"] == ["hint"]
    gate.assert_called_once_with(None)


def test_open_channel_tool_explicit_announce_passes_through():
    from unittest.mock import patch

    decision = {"announce": True, "reason": "explicit", "warnings": []}
    with (
        patch("saturnzap.node.decide_announce", return_value=decision) as gate,
        patch("saturnzap.node.open_channel", return_value="ucid_a") as opener,
    ):
        result = mcp_server.open_channel("02pk", "1.2.3.4:9735", 100_000, announce=True)

    gate.assert_called_once_with(True)
    # The resolved bool is what's passed to node.open_channel, not the raw input.
    opener.assert_called_once_with(
        "02pk", "1.2.3.4:9735", 100_000, announce=True,
    )
    assert result["announce"] is True
    assert "warnings" not in result

