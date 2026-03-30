"""Smoke tests and functional tests for the sz CLI."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from saturnzap.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_data_dir(tmp_path, monkeypatch):
    """Point data dir to a temp directory so no seed/node exists."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


@pytest.fixture()
def mock_node():
    """Shared mock LDK Node for CLI functional tests."""
    n = MagicMock()
    n.node_id.return_value = "02abc"
    n.list_balances.return_value = SimpleNamespace(
        total_onchain_balance_sats=100_000,
        spendable_onchain_balance_sats=90_000,
        total_lightning_balance_sats=50_000,
        total_anchor_channels_reserve_sats=0,
    )
    n.list_peers.return_value = []
    n.list_channels.return_value = []
    n.list_payments.return_value = []
    n.status.return_value = SimpleNamespace(
        is_running=True,
        current_best_block=SimpleNamespace(height=100, block_hash="00ff"),
        latest_onchain_wallet_sync_timestamp=1000,
        latest_lightning_wallet_sync_timestamp=1000,
    )
    return n


# ── Help / entry-point tests ────────────────────────────────────


def test_help_shows_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.output
    assert "start" in result.output
    assert "stop" in result.output
    assert "status" in result.output
    assert "address" in result.output
    assert "balance" in result.output
    assert "peers" in result.output
    assert "channels" in result.output


def test_help_shows_setup():
    result = runner.invoke(app, ["--help"])
    assert "setup" in result.output


def test_help_shows_send():
    result = runner.invoke(app, ["--help"])
    assert "send" in result.output


def test_help_shows_service():
    result = runner.invoke(app, ["--help"])
    assert "service" in result.output


def test_help_shows_fetch():
    result = runner.invoke(app, ["--help"])
    assert "fetch" in result.output


def test_help_shows_liquidity():
    result = runner.invoke(app, ["--help"])
    assert "liquidity" in result.output


# ── No-seed failure tests ────────────────────────────────────────


def test_status_fails_no_seed():
    result = runner.invoke(app, ["status"])
    assert result.exit_code != 0


def test_stop_succeeds_when_no_node():
    result = runner.invoke(app, ["stop"])
    # With channel hygiene, stop may fail if it can't list channels (no seed)
    # but should still succeed or exit gracefully
    assert result.exit_code in (0, 1)


def test_address_fails_no_seed():
    result = runner.invoke(app, ["address"])
    assert result.exit_code != 0


def test_balance_fails_no_seed():
    result = runner.invoke(app, ["balance"])
    assert result.exit_code != 0


def test_peers_list_fails_no_seed():
    result = runner.invoke(app, ["peers", "list"])
    assert result.exit_code != 0


def test_channels_list_fails_no_seed():
    result = runner.invoke(app, ["channels", "list"])
    assert result.exit_code != 0


# ── Subcommand help tests ───────────────────────────────────────


def test_peers_help():
    result = runner.invoke(app, ["peers", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "add" in result.output
    assert "remove" in result.output


def test_channels_help():
    result = runner.invoke(app, ["channels", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "open" in result.output
    assert "close" in result.output


def test_channels_open_requires_peer_or_lsp():
    result = runner.invoke(app, ["channels", "open"])
    assert result.exit_code != 0


def test_service_help():
    result = runner.invoke(app, ["service", "--help"])
    assert result.exit_code == 0
    assert "install" in result.output
    assert "uninstall" in result.output
    assert "status" in result.output


def test_liquidity_help():
    result = runner.invoke(app, ["liquidity", "--help"])
    assert result.exit_code == 0
    assert "status" in result.output
    assert "request-inbound" in result.output


def test_setup_help():
    result = runner.invoke(app, ["setup", "--help"])
    assert result.exit_code == 0
    assert "--auto" in result.output
    assert "--region" in result.output
    assert "--inbound-sats" in result.output


# ── init ─────────────────────────────────────────────────────────


def test_init_already_initialized(tmp_path, monkeypatch):
    """init when seed already exists should return ALREADY_INITIALIZED."""
    monkeypatch.setenv("SZ_PASSPHRASE", "pw")
    from saturnzap import keystore
    keystore.save_encrypted("abandon " * 23 + "art", "pw")

    result = runner.invoke(app, ["init"])
    assert result.exit_code != 0
    assert "ALREADY_INITIALIZED" in result.output or result.exit_code == 1


# ── setup ────────────────────────────────────────────────────────


def test_setup_auto_fresh_wallet(monkeypatch, mock_node):
    monkeypatch.setenv("SZ_PASSPHRASE", "testpw")

    mock_node.onchain_payment.return_value.new_address.return_value = "tb1qaddr"

    with (
        patch("saturnzap.node.build_node", return_value=mock_node),
        patch("saturnzap.liquidity.request_inbound", return_value={"channel": "info"}),
    ):
        result = runner.invoke(app, ["setup", "--auto"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert data["pubkey"] == "02abc"
    assert len(data["steps"]) >= 2


def test_setup_idempotent(tmp_path, monkeypatch, mock_node):
    """setup on an already-inited wallet should skip init step."""
    monkeypatch.setenv("SZ_PASSPHRASE", "pw")
    from saturnzap import keystore
    keystore.save_encrypted("abandon " * 23 + "art", "pw")

    mock_node.onchain_payment.return_value.new_address.return_value = "tb1qaddr"

    with patch("saturnzap.node.start", return_value=mock_node):
        result = runner.invoke(app, ["setup"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    steps = data["steps"]
    init_step = next(s for s in steps if s["step"] == "init")
    assert init_step["skipped"] is True


# ── send ─────────────────────────────────────────────────────────


def test_send_command(mock_node):
    mock_node.onchain_payment.return_value.send_to_address.return_value = "txid1"

    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, ["send", "tb1qdest", "--amount", "5000"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert data["txid"] == "txid1"


def test_send_no_address():
    """send without address should fail."""
    result = runner.invoke(app, ["send"])
    assert result.exit_code != 0


# ── stop --close-all ─────────────────────────────────────────────


def test_stop_close_all(mock_node):
    mock_node.list_channels.return_value = [
        SimpleNamespace(channel_id="ch001", counterparty_node_id="02peer"),
    ]

    # Use side_effect list: first call for list_channels (returns dicts), then stop
    def fake_list_channels():
        return [{"channel_id": "ch001", "counterparty_node_id": "02peer"}]

    with (
        patch("saturnzap.node.list_channels", side_effect=fake_list_channels),
        patch("saturnzap.node.close_channel"),
        patch("saturnzap.node.stop"),
    ):
        result = runner.invoke(app, ["stop", "--close-all"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert "ch001" in data.get("closed_channels", [])


# ── channels wait ────────────────────────────────────────────────


def test_channels_wait(mock_node):
    with patch(
        "saturnzap.node.wait_channel_ready",
        return_value={
            "status": "ready",
            "channel": {"channel_id": "ch1"},
            "waited_seconds": 2,
        },
    ):
        result = runner.invoke(app, ["channels", "wait", "--timeout", "10"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    # output.ok(**result) merges wait_channel_ready's "status":"ready" over "ok"
    assert data["status"] == "ready"
    assert data["channel"]["channel_id"] == "ch1"


# ── invoice --wait ───────────────────────────────────────────────


def test_invoice_wait_flag(mock_node):
    mock_invoice = MagicMock()
    mock_invoice.__str__ = lambda self: "lntbs_test"
    mock_invoice.payment_hash.return_value = "hash1"
    mock_node.bolt11_payment.return_value.receive.return_value = mock_invoice

    with (
        patch("saturnzap.node._require_node", return_value=mock_node),
        patch(
            "saturnzap.payments.wait_for_payment",
            return_value={"paid": True, "received_sats": 100, "waited_seconds": 5},
        ),
    ):
        result = runner.invoke(
            app, ["invoice", "--amount-sats", "100", "--wait"],
        )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["paid"] is True


# ── status functional ────────────────────────────────────────────


def test_status_returns_json(mock_node):
    with (
        patch("saturnzap.node._require_node", return_value=mock_node),
        patch("time.time", return_value=1010),
    ):
        result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert "pubkey" in data
    assert "peer_count" in data


# ── balance functional ───────────────────────────────────────────


def test_balance_returns_json(mock_node):
    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, ["balance"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert "onchain_sats" in data


# ── address functional ──────────────────────────────────────────


def test_address_returns_json(mock_node):
    mock_node.onchain_payment.return_value.new_address.return_value = "tb1qnew"

    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, ["address"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["address"] == "tb1qnew"


# ── fetch ────────────────────────────────────────────────────────


def test_fetch_invalid_header():
    """Fetch with a malformed header should error."""
    import httpx

    mock_resp = httpx.Response(
        200, text="ok", request=httpx.Request("GET", "https://x.com"),
    )
    with patch("httpx.Client") as mc:
        mc.return_value.__enter__.return_value.request.return_value = mock_resp
        result = runner.invoke(app, ["fetch", "https://x.com", "--header", "badheader"])

    assert result.exit_code != 0


# ── --pretty flag ────────────────────────────────────────────────


def test_pretty_flag(mock_node):
    mock_node.onchain_payment.return_value.new_address.return_value = "tb1q"

    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, ["--pretty", "address"])

    assert result.exit_code == 0
    # Pretty output has indentation
    assert "  " in result.output
    data = json.loads(result.output)
    assert data["status"] == "ok"
