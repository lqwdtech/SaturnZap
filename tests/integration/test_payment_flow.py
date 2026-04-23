"""Integration test — payment flow: create invoice → pay → list transactions."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from saturnzap.cli import app

runner = CliRunner()


def test_create_invoice_then_list_transactions(mock_node):
    """Create an invoice, simulate a payment, then list transactions."""
    # Mock invoice creation
    invoice_obj = MagicMock()
    invoice_obj.__str__ = lambda self: "lnbc1000n"
    invoice_obj.payment_hash.return_value = "pay_hash_123"
    mock_node.bolt11_payment().receive.return_value = invoice_obj

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = runner.invoke(
            app, ["invoice", "--amount-sats", "1000", "--memo", "test"]
        )
    assert result.exit_code == 0
    inv_data = json.loads(result.output)
    assert inv_data["payment_hash"] == "pay_hash_123"

    # Simulate payment received (add to mock payments list)
    payment = SimpleNamespace(
        id="pay_id_1",
        kind=SimpleNamespace(
            is_bolt11=lambda: True,
            is_bolt11_jit=lambda: False,
            is_spontaneous=lambda: False,
            is_onchain=lambda: False,
            is_bolt12_offer=lambda: False,
            is_bolt12_refund=lambda: False,
        ),
        direction="INBOUND",
        amount_msat=1_000_000,
        fee_paid_msat=None,
        status="SUCCEEDED",
        latest_update_timestamp=1700000099,
        payment_hash="pay_hash_123",
    )
    mock_node.list_payments.return_value = [payment]

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = runner.invoke(app, ["transactions", "--limit", "5"])
    assert result.exit_code == 0
    tx_data = json.loads(result.output)
    assert tx_data["status"] == "ok"
    assert len(tx_data["transactions"]) == 1
    assert tx_data["transactions"][0]["kind"] == "bolt11"
    assert tx_data["transactions"][0]["amount_sats"] == 1000


def test_pay_invoice_then_verify_in_history(mock_node):
    """Pay an invoice and verify it appears in transaction history."""
    # Mock invoice parsing
    invoice_mock = MagicMock()
    invoice_mock.amount_milli_satoshis.return_value = 500_000  # 500 sats
    invoice_mock.payment_hash.return_value = "out_hash_456"

    mock_node.bolt11_payment().send.return_value = "payment_id_out"
    # Provide terminal-status payment so wait completes immediately.
    sent = SimpleNamespace(
        id="payment_id_out",
        kind=SimpleNamespace(preimage="pre_out"),
        status="PaymentStatus.SUCCEEDED",
    )
    mock_node.list_payments.return_value = [sent]
    mock_node.list_channels.return_value = []

    with (
        patch("saturnzap.payments._require_node", return_value=mock_node),
        patch("saturnzap.payments.Bolt11Invoice.from_str", return_value=invoice_mock),
    ):
        result = runner.invoke(app, [
            "--network", "signet",
            "pay", "--invoice", "lnbc500n1...", "--max-sats", "1000",
        ])
    assert result.exit_code == 0
    pay_data = json.loads(result.output)
    assert pay_data["status"] == "ok"
    assert "payment_id" in pay_data

    # Add to history
    payment = SimpleNamespace(
        id="payment_id_out",
        kind=SimpleNamespace(
            is_bolt11=lambda: True,
            is_bolt11_jit=lambda: False,
            is_spontaneous=lambda: False,
            is_onchain=lambda: False,
            is_bolt12_offer=lambda: False,
            is_bolt12_refund=lambda: False,
        ),
        direction="OUTBOUND",
        amount_msat=500_000,
        fee_paid_msat=1_200,
        status="SUCCEEDED",
        latest_update_timestamp=1700000100,
        payment_hash="out_hash_456",
    )
    mock_node.list_payments.return_value = [payment]

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = runner.invoke(app, ["transactions"])
    tx_data = json.loads(result.output)
    assert tx_data["transactions"][0]["direction"] == "outbound"
    assert tx_data["transactions"][0]["amount_sats"] == 500
