"""Security tests — input validation for addresses, pubkeys, memos, and paths."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("SZ_PASSPHRASE", "testpass")


def _mock_node(**overrides):
    """Create a mock LDK node with sane defaults."""
    n = MagicMock()
    n.list_balances.return_value = SimpleNamespace(
        total_onchain_balance_sats=100_000,
        spendable_onchain_balance_sats=90_000,
        total_lightning_balance_sats=50_000,
        total_anchor_channels_reserve_sats=0,
    )
    for k, v in overrides.items():
        setattr(n, k, v)
    return n


# ── Oversized inputs ─────────────────────────────────────────────


def test_oversized_address_handled():
    """An absurdly large address should not crash the wallet."""
    from saturnzap import node

    mock = _mock_node()
    # LDK should reject the garbage address gracefully
    mock.onchain_payment().send_to_address.side_effect = ValueError("invalid address")

    with patch.object(node, "_require_node", return_value=mock):  # noqa: SIM117
        with pytest.raises((SystemExit, ValueError)):
            node.send_onchain("A" * 100_000, 1000)


def test_oversized_pubkey_keysend():
    """A 100KB pubkey string should fail, not OOM."""
    from saturnzap import payments

    mock = _mock_node()
    mock.spontaneous_payment().send.side_effect = ValueError("invalid pubkey")

    with patch("saturnzap.payments._require_node", return_value=mock):  # noqa: SIM117
        with pytest.raises((SystemExit, ValueError)):
            payments.keysend("0" * 100_000, 1000)


# ── Path traversal ───────────────────────────────────────────────


def test_l402_cache_key_no_directory_traversal():
    """Token cache filenames must not contain path separators."""
    from saturnzap.l402 import _cache_key

    key = _cache_key("https://evil.com/../../../etc/passwd")
    assert "/" not in key
    assert "\\" not in key
    assert ".." not in key
    assert len(key) == 32  # SHA256 hex truncated


def test_l402_cache_key_is_deterministic():
    from saturnzap.l402 import _cache_key

    assert _cache_key("https://example.com") == _cache_key("https://example.com")


# ── Special characters in memo ───────────────────────────────────


def test_invoice_memo_special_chars_passed_through():
    """Invoice memos with special chars should not cause JSON encoding errors."""
    from saturnzap import payments

    mock = _mock_node()
    invoice_mock = MagicMock()
    invoice_mock.payment_hash.return_value = "abc123"
    mock.bolt11_payment().receive.return_value = invoice_mock

    memo = '<script>alert("xss")</script>\'; DROP TABLE users;--'

    with patch("saturnzap.payments._require_node", return_value=mock):
        result = payments.create_invoice(1000, memo=memo)
        # Should succeed — memo is passed to LDK, not interpreted
        assert "payment_hash" in result


# ── Invalid invoice formats ──────────────────────────────────────


def test_pay_garbage_invoice_gives_error():
    """Paying a non-Lightning invoice string should fail gracefully."""
    from ldk_node.ldk_node import NodeError

    from saturnzap import payments

    mock = _mock_node()

    with patch("saturnzap.payments._require_node", return_value=mock):  # noqa: SIM117
        with pytest.raises((SystemExit, NodeError.InvalidInvoice)):
            # Bolt11Invoice.from_str should raise on garbage
            payments.pay_invoice("not-a-real-invoice")


# ── L402 challenge parsing edge cases ────────────────────────────


def test_l402_parse_empty_header():
    """Empty WWW-Authenticate should fail gracefully."""
    from saturnzap.l402 import parse_l402_challenge

    with pytest.raises(SystemExit):
        parse_l402_challenge("")


def test_l402_parse_missing_invoice():
    """Header with macaroon but no invoice should fail."""
    from saturnzap.l402 import parse_l402_challenge

    with pytest.raises(SystemExit):
        parse_l402_challenge("LSAT macaroon123")


def test_l402_parse_sql_injection_in_header():
    """SQL injection in header should be safely unparseable."""
    from saturnzap.l402 import parse_l402_challenge

    with pytest.raises(SystemExit):
        parse_l402_challenge("LSAT '; DROP TABLE tokens;--")
