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
# Tool registration — verify all 22 tools are present
# ---------------------------------------------------------------------------

EXPECTED_TOOLS = [
    "is_initialized",
    "init_wallet",
    "get_status",
    "stop_node",
    "new_onchain_address",
    "get_balance",
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
