"""Tests for saturnzap.payments — invoice, pay, keysend, transactions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from saturnzap import payments
from saturnzap.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


@pytest.fixture()
def mock_node():
    """Return a MagicMock that behaves like an LDK Node."""
    node = MagicMock()
    # Default balances
    node.list_balances.return_value = SimpleNamespace(
        total_lightning_balance_sats=50_000,
        spendable_onchain_balance_sats=100_000,
        total_onchain_balance_sats=100_000,
        total_anchor_channels_reserve_sats=0,
    )
    return node


# ── CLI help / smoke tests ───────────────────────────────────────


def test_invoice_help():
    from tests.conftest import strip_ansi

    result = runner.invoke(app, ["invoice", "--help"])
    assert result.exit_code == 0
    out = strip_ansi(result.output)
    assert "--amount-sats" in out
    assert "--memo" in out
    assert "--expiry" in out


def test_pay_help():
    from tests.conftest import strip_ansi

    result = runner.invoke(app, ["pay", "--help"])
    assert result.exit_code == 0
    out = strip_ansi(result.output)
    assert "--invoice" in out
    assert "--max-sats" in out


def test_keysend_help():
    from tests.conftest import strip_ansi

    result = runner.invoke(app, ["keysend", "--help"])
    assert result.exit_code == 0
    out = strip_ansi(result.output)
    assert "--pubkey" in out
    assert "--amount-sats" in out


def test_transactions_help():
    from tests.conftest import strip_ansi

    result = runner.invoke(app, ["transactions", "--help"])
    assert result.exit_code == 0
    out = strip_ansi(result.output)
    assert "--limit" in out


def test_invoice_fails_no_seed():
    result = runner.invoke(app, ["invoice", "--amount-sats", "1000"])
    assert result.exit_code != 0


def test_pay_requires_invoice():
    result = runner.invoke(app, ["pay"])
    assert result.exit_code != 0


def test_keysend_requires_options():
    result = runner.invoke(app, ["keysend"])
    assert result.exit_code != 0


def test_transactions_fails_no_seed():
    result = runner.invoke(app, ["transactions"])
    assert result.exit_code != 0


# ── create_invoice ───────────────────────────────────────────────


def test_create_invoice_returns_dict(mock_node):
    mock_invoice = MagicMock()
    mock_invoice.__str__ = lambda self: "lntbs1000..."
    mock_invoice.payment_hash.return_value = "hash123"
    mock_node.bolt11_payment.return_value.receive.return_value = mock_invoice

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = payments.create_invoice(1000, memo="test", expiry_secs=3600)

    assert result["invoice"] == "lntbs1000..."
    assert result["amount_sats"] == 1000
    assert result["payment_hash"] == "hash123"
    assert result["expiry_secs"] == 3600


def test_create_invoice_default_memo(mock_node):
    mock_invoice = MagicMock()
    mock_invoice.__str__ = lambda self: "lntbs..."
    mock_invoice.payment_hash.return_value = "hash"
    mock_node.bolt11_payment.return_value.receive.return_value = mock_invoice

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = payments.create_invoice(500)

    assert result["amount_sats"] == 500


# ── create_variable_invoice ──────────────────────────────────────


def test_create_variable_invoice(mock_node):
    mock_invoice = MagicMock()
    mock_invoice.__str__ = lambda self: "lntbs_var..."
    mock_invoice.payment_hash.return_value = "varhash"
    mock_node.bolt11_payment.return_value.receive_variable_amount.return_value = (
        mock_invoice
    )

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = payments.create_variable_invoice(memo="donate")

    assert result["invoice"] == "lntbs_var..."
    assert result["amount_sats"] is None
    assert result["payment_hash"] == "varhash"


# ── pay_invoice ──────────────────────────────────────────────────


def test_pay_invoice_success(mock_node):
    mock_inv = MagicMock()
    mock_inv.amount_milli_satoshis.return_value = 10_000_000  # 10k sats
    mock_inv.payment_hash.return_value = "payhash"
    mock_node.bolt11_payment.return_value.send.return_value = "payid123"

    # Mock list_payments so _extract_preimage finds the payment
    paid = SimpleNamespace(
        id="payid123",
        kind=SimpleNamespace(preimage="deadbeef01234567"),
    )
    mock_node.list_payments.return_value = [paid]

    with (
        patch("saturnzap.payments._require_node", return_value=mock_node),
        patch("ldk_node.Bolt11Invoice.from_str", return_value=mock_inv),
    ):
        result = payments.pay_invoice("lntbs10000...")

    assert result["payment_id"] == "payid123"
    assert result["payment_hash"] == "payhash"
    assert result["amount_msat"] == 10_000_000
    assert result["preimage"] == "deadbeef01234567"


def test_pay_invoice_exceeds_max_sats(mock_node):
    mock_inv = MagicMock()
    mock_inv.amount_milli_satoshis.return_value = 500_000  # 500 sats

    with (
        patch("saturnzap.payments._require_node", return_value=mock_node),
        patch("ldk_node.Bolt11Invoice.from_str", return_value=mock_inv),
        pytest.raises(SystemExit),
    ):
        payments.pay_invoice("lntbs500...", max_sats=100)


def test_pay_invoice_insufficient_funds(mock_node):
    mock_inv = MagicMock()
    mock_inv.amount_milli_satoshis.return_value = 100_000_000  # 100k sats
    mock_node.list_balances.return_value.total_lightning_balance_sats = 50_000

    with (
        patch("saturnzap.payments._require_node", return_value=mock_node),
        patch("ldk_node.Bolt11Invoice.from_str", return_value=mock_inv),
        pytest.raises(SystemExit),
    ):
        payments.pay_invoice("lntbs100000...")


def test_pay_invoice_no_amount_skips_balance_check(mock_node):
    """Variable-amount invoices skip the pre-flight balance check."""
    mock_inv = MagicMock()
    mock_inv.amount_milli_satoshis.return_value = None
    mock_inv.payment_hash.return_value = "hash"
    mock_node.bolt11_payment.return_value.send.return_value = "pid"
    mock_node.list_payments.return_value = []

    with (
        patch("saturnzap.payments._require_node", return_value=mock_node),
        patch("ldk_node.Bolt11Invoice.from_str", return_value=mock_inv),
    ):
        result = payments.pay_invoice("lntbs_var...")

    assert result["payment_id"] == "pid"
    assert result["amount_msat"] is None
    assert result["preimage"] is None


# ── _extract_preimage ────────────────────────────────────────────


def test_extract_preimage_found():
    """Preimage should be extracted from a matching payment."""
    node = MagicMock()
    paid = SimpleNamespace(
        id="pid_abc",
        kind=SimpleNamespace(preimage="cafebabe12345678"),
    )
    node.list_payments.return_value = [paid]

    result = payments._extract_preimage(node, "pid_abc")
    assert result == "cafebabe12345678"


def test_extract_preimage_none_when_missing():
    """If no matching payment found, return None (after brief polling)."""
    node = MagicMock()
    node.list_payments.return_value = []

    with (
        patch("saturnzap.payments._PREIMAGE_POLL_ATTEMPTS", 1),
        patch("saturnzap.payments._PREIMAGE_POLL_INTERVAL", 0),
    ):
        result = payments._extract_preimage(node, "nonexistent")
    assert result is None


def test_extract_preimage_none_when_preimage_not_set():
    """If payment exists but preimage is None, return None."""
    node = MagicMock()
    paid = SimpleNamespace(
        id="pid_abc",
        kind=SimpleNamespace(preimage=None),
    )
    node.list_payments.return_value = [paid]

    with (
        patch("saturnzap.payments._PREIMAGE_POLL_ATTEMPTS", 1),
        patch("saturnzap.payments._PREIMAGE_POLL_INTERVAL", 0),
    ):
        result = payments._extract_preimage(node, "pid_abc")
    assert result is None


# ── keysend ──────────────────────────────────────────────────────


def test_keysend_success(mock_node):
    mock_node.spontaneous_payment.return_value.send.return_value = "ksend_id"

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = payments.keysend("02abc...", 1000)

    assert result["payment_id"] == "ksend_id"
    assert result["pubkey"] == "02abc..."
    assert result["amount_sats"] == 1000


def test_keysend_insufficient_funds(mock_node):
    mock_node.list_balances.return_value.total_lightning_balance_sats = 500

    with (
        patch("saturnzap.payments._require_node", return_value=mock_node),
        pytest.raises(SystemExit),
    ):
        payments.keysend("02abc...", 1000)


# ── list_transactions ────────────────────────────────────────────


def _make_payment(pid, kind_str, direction_str, status_str, amount_msat, fee_msat, ts):
    """Create a fake payment object."""
    p = SimpleNamespace()
    p.id = pid
    p.kind = SimpleNamespace()
    p.kind.is_bolt11 = lambda: "bolt11" in kind_str
    p.kind.is_bolt11_jit = lambda: "jit" in kind_str
    p.kind.is_spontaneous = lambda: "spontaneous" in kind_str
    p.kind.is_onchain = lambda: "onchain" in kind_str
    p.kind.is_bolt12_offer = lambda: "offer" in kind_str
    p.kind.is_bolt12_refund = lambda: "refund" in kind_str
    p.direction = f"PaymentDirection.{direction_str}"
    p.status = f"PaymentStatus.{status_str}"
    p.amount_msat = amount_msat
    p.fee_paid_msat = fee_msat
    p.latest_update_timestamp = ts
    p.payment_hash = f"hash_{pid}"
    return p


def test_list_transactions_returns_correct_shape(mock_node):
    mock_node.list_payments.return_value = [
        _make_payment("p1", "bolt11", "OUTBOUND", "SUCCEEDED", 10_000, 100, 1000),
        _make_payment("p2", "spontaneous", "INBOUND", "PENDING", 5_000, None, 999),
    ]

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = payments.list_transactions()

    assert len(result) == 2
    assert result[0]["payment_id"] == "p1"
    assert result[0]["kind"] == "bolt11"
    assert result[0]["direction"] == "outbound"
    assert result[0]["status"] == "succeeded"
    assert result[0]["amount_sats"] == 10
    assert result[0]["fee_sats"] == 0  # 100 // 1000
    assert result[1]["kind"] == "spontaneous"
    assert result[1]["direction"] == "inbound"


def test_list_transactions_limit(mock_node):
    mock_node.list_payments.return_value = [
        _make_payment(f"p{i}", "bolt11", "OUTBOUND", "SUCCEEDED", 1000, 10, 1000 - i)
        for i in range(20)
    ]

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = payments.list_transactions(limit=5)

    assert len(result) == 5


def test_list_transactions_sorted_by_timestamp(mock_node):
    mock_node.list_payments.return_value = [
        _make_payment("old", "bolt11", "OUTBOUND", "SUCCEEDED", 1000, 10, 100),
        _make_payment("new", "bolt11", "OUTBOUND", "SUCCEEDED", 1000, 10, 999),
    ]

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = payments.list_transactions()

    assert result[0]["payment_id"] == "new"
    assert result[1]["payment_id"] == "old"


# ── wait_for_payment ─────────────────────────────────────────────


def test_wait_for_payment_succeeds(mock_node):
    paid_payment = SimpleNamespace(
        payment_hash="target_hash",
        direction="PaymentDirection.INBOUND",
        status="PaymentStatus.SUCCEEDED",
        amount_msat=50_000,
    )
    mock_node.list_payments.return_value = [paid_payment]

    with (
        patch("saturnzap.payments._require_node", return_value=mock_node),
        patch("time.sleep"),
    ):
        result = payments.wait_for_payment("target_hash", timeout=10, poll_interval=1)

    assert result["paid"] is True
    assert result["received_sats"] == 50


def test_wait_for_payment_timeout(mock_node):
    mock_node.list_payments.return_value = []  # Never arrives

    with (
        patch("saturnzap.payments._require_node", return_value=mock_node),
        patch("time.sleep"),
        patch("time.monotonic", side_effect=[0, 0, 11]),  # start, check, past deadline
    ):
        result = payments.wait_for_payment("nope", timeout=10, poll_interval=1)

    assert result["paid"] is False
    assert result["waited_seconds"] == 10


# ── Enum conversion helpers ──────────────────────────────────────


def test_payment_kind_str_bolt11():
    kind = SimpleNamespace(
        is_bolt11=lambda: True, is_bolt11_jit=lambda: False,
        is_spontaneous=lambda: False, is_onchain=lambda: False,
        is_bolt12_offer=lambda: False, is_bolt12_refund=lambda: False,
    )
    assert payments._payment_kind_str(kind) == "bolt11"


def test_payment_kind_str_onchain():
    kind = SimpleNamespace(
        is_bolt11=lambda: False, is_bolt11_jit=lambda: False,
        is_spontaneous=lambda: False, is_onchain=lambda: True,
        is_bolt12_offer=lambda: False, is_bolt12_refund=lambda: False,
    )
    assert payments._payment_kind_str(kind) == "onchain"


def test_payment_kind_str_unknown():
    kind = SimpleNamespace(
        is_bolt11=lambda: False, is_bolt11_jit=lambda: False,
        is_spontaneous=lambda: False, is_onchain=lambda: False,
        is_bolt12_offer=lambda: False, is_bolt12_refund=lambda: False,
    )
    assert payments._payment_kind_str(kind) == "unknown"


def test_payment_direction_str():
    assert payments._payment_direction_str("PaymentDirection.INBOUND") == "inbound"
    assert payments._payment_direction_str("PaymentDirection.OUTBOUND") == "outbound"


def test_payment_status_str():
    assert payments._payment_status_str("PaymentStatus.SUCCEEDED") == "succeeded"
    assert payments._payment_status_str("PaymentStatus.PENDING") == "pending"
    assert payments._payment_status_str("PaymentStatus.FAILED") == "failed"
    assert payments._payment_status_str("PaymentStatus.OTHER") == "unknown"
