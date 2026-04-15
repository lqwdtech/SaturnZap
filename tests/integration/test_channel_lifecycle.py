"""Integration test — channel lifecycle: open → wait ready → list → close."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from typer.testing import CliRunner

from saturnzap.cli import app

runner = CliRunner()


def _make_channel(channel_id="ch01", is_usable=True, is_ready=True):
    return SimpleNamespace(
        channel_id=channel_id,
        counterparty_node_id="03" + "cd" * 32,
        channel_value_sats=100_000,
        outbound_capacity_msat=50_000_000,
        inbound_capacity_msat=50_000_000,
        is_usable=is_usable,
        is_channel_ready=is_ready,
        is_outbound=True,
        is_announced=False,
        confirmations=6,
        confirmations_required=3,
        funding_txo=None,
    )


def test_channel_open_wait_list_close(mock_node):
    """Open a channel, wait for ready, list it, then close."""
    # Step 1: Open channel
    mock_node.connect.return_value = None
    mock_node.open_channel.return_value = "user_ch_01"
    # Channel must survive the post-open handshake check
    ch_pending = _make_channel("user_ch_01", is_usable=False, is_ready=False)
    mock_node.list_channels.return_value = [ch_pending]

    peer = "03" + "cd" * 32 + "@1.2.3.4:9735"
    with (
        patch("saturnzap.node._require_node", return_value=mock_node),
        patch("time.sleep"),
    ):
        result = runner.invoke(app, [
            "--network", "signet",
            "channels", "open",
            "--peer", peer,
            "--amount-sats", "100000",
        ])
    assert result.exit_code == 0
    open_data = json.loads(result.output)
    assert open_data["status"] == "ok"

    # Step 2: Wait for channel ready
    ch = _make_channel("user_ch_01", is_usable=True, is_ready=True)
    mock_node.list_channels.return_value = [ch]

    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, [
            "channels", "wait",
            "--channel-id", "user_ch_01",
            "--timeout", "5",
        ])
    assert result.exit_code == 0
    wait_data = json.loads(result.output)
    assert wait_data["status"] == "ready"

    # Step 3: List channels
    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, ["channels", "list"])
    assert result.exit_code == 0
    list_data = json.loads(result.output)
    assert list_data["status"] == "ok"
    assert len(list_data["channels"]) == 1

    # Step 4: Close channel
    mock_node.close_channel.return_value = None
    counterparty = "03" + "cd" * 32
    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, [
            "channels", "close",
            "--channel-id", "user_ch_01",
            "--counterparty", counterparty,
        ])
    assert result.exit_code == 0
    close_data = json.loads(result.output)
    assert close_data["status"] == "ok"
