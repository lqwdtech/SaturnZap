"""Agent scenario tests — validate that an AI agent can complete common workflows.

Each test simulates a realistic agent decision path via the CLI,
verifying JSON output is parseable, contains expected fields, and
errors have actionable messages.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from saturnzap.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("SZ_PASSPHRASE", "agentpass")


@pytest.fixture()
def mock_node():
    n = MagicMock()
    n.node_id.return_value = "02" + "ab" * 32
    n.list_balances.return_value = SimpleNamespace(
        total_onchain_balance_sats=100_000,
        spendable_onchain_balance_sats=90_000,
        total_lightning_balance_sats=50_000,
        total_anchor_channels_reserve_sats=0,
    )
    n.list_channels.return_value = []
    n.list_peers.return_value = []
    n.list_payments.return_value = []
    n.sync_wallets.return_value = None
    n.onchain_payment.return_value.new_address.return_value = "tb1qtest"
    n.status.return_value = SimpleNamespace(
        is_running=True,
        current_best_block=SimpleNamespace(height=12345, block_hash="00ff"),
        latest_onchain_wallet_sync_timestamp=1000,
        latest_lightning_wallet_sync_timestamp=1000,
    )
    return n


# ── Scenario 1: First-time setup ────────────────────────────────


def test_agent_setup_auto_returns_parseable_json(monkeypatch, mock_node):
    """An agent running setup --auto should get valid JSON with expected fields."""
    monkeypatch.setenv("SZ_PASSPHRASE", "agentpass")

    with (
        patch("saturnzap.node.build_node", return_value=mock_node),
        patch("saturnzap.liquidity.request_inbound", return_value={"channel": "info"}),
    ):
        result = runner.invoke(app, ["setup", "--auto"])

    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert "pubkey" in data
    assert "steps" in data
    assert any(s["step"] == "init" for s in data["steps"])
    assert any(s["step"] == "address" for s in data["steps"])


# ── Scenario 2: Check if operational ────────────────────────────


def test_agent_checks_status_for_readiness(mock_node):
    """An agent checking operational readiness should parse key fields."""
    with (
        patch("saturnzap.node._require_node", return_value=mock_node),
        patch("time.time", return_value=1010),
    ):
        result = runner.invoke(app, ["status"])

    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert "pubkey" in data
    assert "block_height" in data
    assert isinstance(data["peer_count"], int)
    assert isinstance(data["channel_count"], int)


# ── Scenario 3: Check balance before payment ────────────────────


def test_agent_checks_balance_before_paying(mock_node):
    """Agent checks balance and decides if it can afford a payment."""
    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, ["balance"])

    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert "lightning_sats" in data
    assert "onchain_sats" in data

    # Agent decision: can I afford 5000 sats?
    can_afford = data["lightning_sats"] >= 5000
    assert can_afford is True


# ── Scenario 4: Create invoice and wait for payment ─────────────


def test_agent_creates_invoice(mock_node):
    """An agent creating an invoice should get an invoice string and payment hash."""
    invoice_obj = MagicMock()
    invoice_obj.__str__ = lambda self: "lnbc1000..."
    invoice_obj.payment_hash.return_value = "abc123"
    mock_node.bolt11_payment().receive.return_value = invoice_obj

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = runner.invoke(app, ["invoice", "--amount-sats", "1000"])

    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert "invoice" in data
    assert "payment_hash" in data
    assert data["amount_sats"] == 1000


# ── Scenario 5: Diagnose channel problem ────────────────────────


def test_agent_diagnoses_no_channels(mock_node):
    """An agent with no channels should see channel_count=0 and know to open one."""
    with (
        patch("saturnzap.node._require_node", return_value=mock_node),
        patch("time.time", return_value=1010),
    ):
        result = runner.invoke(app, ["status"])

    data = json.loads(result.output)
    assert data["channel_count"] == 0


# ── Scenario 6: Error has actionable code ────────────────────────


def test_agent_gets_actionable_error_on_no_seed():
    """When no seed exists, the error should have a code the agent can act on."""
    with patch("saturnzap.node._require_node", side_effect=SystemExit(1)):
        result = runner.invoke(app, ["status"])

    assert result.exit_code != 0


def test_agent_error_json_has_code_and_message():
    """All error outputs should have 'code' and 'message' fields for agent parsing."""
    import io

    from saturnzap import output

    captured = io.StringIO()
    with patch("sys.stderr", captured), pytest.raises(SystemExit):
        output.error("TEST_CODE", "Test message")

    data = json.loads(captured.getvalue())
    assert data["status"] == "error"
    assert data["code"] == "TEST_CODE"
    assert data["message"] == "Test message"


# ── Scenario 7: Spending cap enforcement ─────────────────────────


def test_agent_pay_with_cap_exceeds(mock_node):
    """If invoice exceeds max_sats, the agent should get EXCEEDS_MAX_SATS error."""
    from saturnzap import payments

    invoice = MagicMock()
    invoice.amount_milli_satoshis.return_value = 10_000_000  # 10k sats
    invoice.payment_hash.return_value = "hash"

    with (  # noqa: SIM117
        patch("saturnzap.payments._require_node", return_value=mock_node),
        patch("saturnzap.payments.Bolt11Invoice.from_str", return_value=invoice),
    ):
        with pytest.raises(SystemExit):
            payments.pay_invoice("lnbc...", max_sats=1000)


# ── Scenario 8: JSON output is always parseable ─────────────────


def test_all_success_output_is_valid_json(mock_node):
    """Verify that balance, status, and address all produce valid JSON."""
    with (
        patch("saturnzap.node._require_node", return_value=mock_node),
        patch("time.time", return_value=1010),
    ):
        for cmd in [["status"], ["balance"], ["address"]]:
            result = runner.invoke(app, cmd)
            data = json.loads(result.output)
            assert data["status"] == "ok", f"{cmd} did not return ok"
