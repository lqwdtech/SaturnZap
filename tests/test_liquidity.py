"""Tests for saturnzap.liquidity — health scoring, recommendations, requests."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from saturnzap import liquidity
from saturnzap.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


# ── Health score ─────────────────────────────────────────────────


def _make_channel(
    outbound_msat: int = 50_000_000,
    inbound_msat: int = 50_000_000,
    value_sats: int = 100_000,
    usable: bool = True,
    ready: bool = True,
    peer: str = "aabbcc",
) -> dict:
    return {
        "channel_id": "ch01",
        "counterparty_node_id": peer,
        "channel_value_sats": value_sats,
        "outbound_capacity_msat": outbound_msat,
        "inbound_capacity_msat": inbound_msat,
        "is_channel_ready": ready,
        "is_usable": usable,
        "is_outbound": True,
        "is_announced": False,
        "confirmations": 6,
        "funding_txo": None,
    }


def test_health_score_balanced():
    ch = _make_channel(outbound_msat=50_000_000, value_sats=100_000)
    assert liquidity._health_score(ch) == 100


def test_health_score_all_outbound():
    ch = _make_channel(outbound_msat=100_000_000, value_sats=100_000)
    assert liquidity._health_score(ch) == 0


def test_health_score_no_outbound():
    ch = _make_channel(outbound_msat=0, value_sats=100_000)
    assert liquidity._health_score(ch) == 0


def test_health_score_20_percent():
    ch = _make_channel(outbound_msat=20_000_000, value_sats=100_000)
    assert liquidity._health_score(ch) == 40


def test_health_score_80_percent():
    ch = _make_channel(outbound_msat=80_000_000, value_sats=100_000)
    assert liquidity._health_score(ch) == 40


def test_health_score_zero_capacity():
    ch = _make_channel(outbound_msat=0, value_sats=0)
    assert liquidity._health_score(ch) == 0


# ── Health label ─────────────────────────────────────────────────


def test_label_healthy():
    assert liquidity._health_label(40) == "healthy"
    assert liquidity._health_label(100) == "healthy"


def test_label_warning():
    assert liquidity._health_label(20) == "warning"
    assert liquidity._health_label(39) == "warning"


def test_label_critical():
    assert liquidity._health_label(0) == "critical"
    assert liquidity._health_label(19) == "critical"


# ── post_payment_warnings ────────────────────────────────────────


def test_post_payment_warnings_healthy_channels():
    """No warnings when outbound is above threshold."""
    ch = _make_channel(outbound_msat=50_000_000, value_sats=100_000)
    with patch("saturnzap.liquidity.load_liquidity_config", return_value=_DEFAULT_CFG):
        result = liquidity.post_payment_warnings([ch])
    assert result == []


def test_post_payment_warnings_low_outbound():
    """Warn when outbound drops below threshold."""
    ch = _make_channel(outbound_msat=15_000_000, value_sats=100_000)  # 15%
    with patch("saturnzap.liquidity.load_liquidity_config", return_value=_DEFAULT_CFG):
        result = liquidity.post_payment_warnings([ch])
    assert len(result) == 1
    assert "Low outbound" in result[0]
    assert "15%" in result[0]


def test_post_payment_warnings_multiple_low():
    """Multiple low channels produce multiple warnings."""
    ch1 = _make_channel(outbound_msat=10_000_000, value_sats=100_000, peer="aaa111")
    ch2 = _make_channel(outbound_msat=5_000_000, value_sats=100_000, peer="bbb222")
    with patch("saturnzap.liquidity.load_liquidity_config", return_value=_DEFAULT_CFG):
        result = liquidity.post_payment_warnings([ch1, ch2])
    assert len(result) == 2


def test_post_payment_warnings_empty_channels():
    """No crash with empty channel list."""
    with patch("saturnzap.liquidity.load_liquidity_config", return_value=_DEFAULT_CFG):
        result = liquidity.post_payment_warnings([])
    assert result == []


def test_post_payment_warnings_zero_capacity():
    """Zero-capacity channel is skipped (no division by zero)."""
    ch = _make_channel(outbound_msat=0, value_sats=0)
    with patch("saturnzap.liquidity.load_liquidity_config", return_value=_DEFAULT_CFG):
        result = liquidity.post_payment_warnings([ch])
    assert result == []


def test_post_payment_warnings_unusable_channel_ignored():
    """Non-usable channels are not checked for outbound warnings."""
    ch = _make_channel(outbound_msat=5_000_000, value_sats=100_000, usable=False)
    with patch("saturnzap.liquidity.load_liquidity_config", return_value=_DEFAULT_CFG):
        result = liquidity.post_payment_warnings([ch])
    assert result == []


# ── balance_warnings ─────────────────────────────────────────────


def test_balance_warnings_has_channels_healthy():
    """No warnings when channels exist and are healthy."""
    ch = _make_channel(outbound_msat=50_000_000, value_sats=100_000)
    balance = {"spendable_onchain_sats": 1000, "channels": [ch]}
    result = liquidity.balance_warnings(balance)
    assert result == []


def test_balance_warnings_no_channels_has_funds():
    """Warn about opening channels when on-chain funds available."""
    balance = {"spendable_onchain_sats": 50_000, "channels": []}
    result = liquidity.balance_warnings(balance)
    assert len(result) == 1
    assert "sz channels open" in result[0]


def test_balance_warnings_no_channels_no_funds():
    """Warn about funding when no channels and no funds."""
    balance = {"spendable_onchain_sats": 0, "channels": []}
    result = liquidity.balance_warnings(balance)
    assert len(result) == 1
    assert "sz address" in result[0]


def test_balance_warnings_all_critical():
    """Warn when all usable channels are critically low."""
    ch = _make_channel(outbound_msat=5_000_000, value_sats=100_000)  # score=10
    balance = {"spendable_onchain_sats": 1000, "channels": [ch]}
    result = liquidity.balance_warnings(balance)
    assert len(result) == 1
    assert "critically low" in result[0]


def test_balance_warnings_mixed_health_no_warning():
    """No critical warning when at least one channel is healthy."""
    healthy = _make_channel(outbound_msat=50_000_000, value_sats=100_000)
    low = _make_channel(outbound_msat=5_000_000, value_sats=100_000)
    balance = {"spendable_onchain_sats": 1000, "channels": [healthy, low]}
    result = liquidity.balance_warnings(balance)
    assert result == []


# ── Recommendations ──────────────────────────────────────────────

_DEFAULT_CFG = {"outbound_threshold_percent": 20, "inbound_threshold_percent": 20}


def test_recs_no_channels():
    balance = {"spendable_onchain_sats": 50000}
    recs = liquidity._generate_recommendations([], balance, _DEFAULT_CFG)
    assert any("No channels" in r for r in recs)
    assert any("On-chain funds" in r for r in recs)


def test_recs_no_channels_no_funds():
    balance = {"spendable_onchain_sats": 0}
    recs = liquidity._generate_recommendations([], balance, _DEFAULT_CFG)
    assert any("No channels" in r for r in recs)
    assert not any("On-chain funds" in r for r in recs)


def test_recs_low_outbound():
    ch = _make_channel(
        outbound_msat=5_000_000, inbound_msat=95_000_000,
        value_sats=100_000,
    )
    recs = liquidity._generate_recommendations([ch], {}, _DEFAULT_CFG)
    assert any("Low outbound" in r for r in recs)


def test_recs_low_inbound():
    ch = _make_channel(
        outbound_msat=95_000_000, inbound_msat=5_000_000,
        value_sats=100_000,
    )
    recs = liquidity._generate_recommendations([ch], {}, _DEFAULT_CFG)
    assert any("Low inbound" in r for r in recs)


def test_recs_balanced_no_warnings():
    ch = _make_channel(
        outbound_msat=50_000_000, inbound_msat=50_000_000,
        value_sats=100_000,
    )
    recs = liquidity._generate_recommendations([ch], {}, _DEFAULT_CFG)
    assert not any("Low" in r for r in recs)


def test_recs_pending_channel():
    ch = _make_channel(usable=False, ready=False)
    recs = liquidity._generate_recommendations([ch], {}, _DEFAULT_CFG)
    assert any("awaiting confirmation" in r for r in recs)


# ── get_status (mocked) ─────────────────────────────────────────


def test_get_status_with_channels():
    ch = _make_channel()
    balance = {
        "onchain_sats": 50000,
        "spendable_onchain_sats": 50000,
        "lightning_sats": 100000,
        "anchor_reserve_sats": 0,
        "channels": [ch],
    }
    with patch("saturnzap.liquidity.node") as mock_node, \
         patch("saturnzap.liquidity.load_liquidity_config", return_value=_DEFAULT_CFG):
        mock_node.get_balance.return_value = balance
        result = liquidity.get_status()

    assert result["total_channels"] == 1
    assert result["usable_channels"] == 1
    assert result["channels"][0]["health_score"] == 100
    assert result["channels"][0]["health_label"] == "healthy"
    assert result["onchain_sats"] == 50000
    assert result["lightning_sats"] == 100000


def test_get_status_empty():
    balance = {
        "onchain_sats": 0,
        "spendable_onchain_sats": 0,
        "lightning_sats": 0,
        "anchor_reserve_sats": 0,
        "channels": [],
    }
    with patch("saturnzap.liquidity.node") as mock_node, \
         patch("saturnzap.liquidity.load_liquidity_config", return_value=_DEFAULT_CFG):
        mock_node.get_balance.return_value = balance
        result = liquidity.get_status()

    assert result["total_channels"] == 0
    assert result["usable_channels"] == 0
    assert any("No channels" in r for r in result["recommendations"])


# ── CLI ──────────────────────────────────────────────────────────


def test_liquidity_help():
    result = runner.invoke(app, ["liquidity", "--help"])
    assert result.exit_code == 0
    assert "status" in result.output
    assert "request-inbound" in result.output


def test_liquidity_status_help():
    result = runner.invoke(app, ["liquidity", "status", "--help"])
    assert result.exit_code == 0


def test_liquidity_request_inbound_help():
    from tests.conftest import strip_ansi

    result = runner.invoke(app, ["liquidity", "request-inbound", "--help"])
    assert result.exit_code == 0
    out = strip_ansi(result.output)
    assert "--amount-sats" in out
    assert "--region" in out


def test_liquidity_status_cli_mocked():
    balance = {
        "onchain_sats": 1000,
        "spendable_onchain_sats": 1000,
        "lightning_sats": 0,
        "anchor_reserve_sats": 0,
        "channels": [],
    }
    with patch("saturnzap.liquidity.node") as mock_node, \
         patch("saturnzap.liquidity.load_liquidity_config", return_value=_DEFAULT_CFG):
        mock_node.get_balance.return_value = balance
        result = runner.invoke(app, ["liquidity", "status"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert data["total_channels"] == 0


def test_request_inbound_uses_announce_gate():
    """request_inbound consults decide_announce and surfaces the decision."""
    decision = {"announce": True, "reason": "reachable", "warnings": []}
    target = {
        "pubkey": "02lqwd",
        "address": "1.2.3.4:9735",
        "alias": "LQWD-Test",
        "region": "TEST",
    }
    with (
        patch("saturnzap.liquidity.lqwd.get_nearest", return_value=target),
        patch("saturnzap.node.connect_peer"),
        patch("saturnzap.node.decide_announce", return_value=decision) as gate,
        patch("saturnzap.node.open_channel", return_value="ucid_inbound") as opener,
    ):
        result = liquidity.request_inbound(500_000)

    gate.assert_called_once_with(None)
    # announce= flag is forwarded to node.open_channel.
    _, kwargs = opener.call_args
    assert kwargs["announce"] is True
    assert result["announce"] is True
    assert result["announce_reason"] == "reachable"
    assert "warnings" not in result


def test_request_inbound_unreachable_emits_hint():
    decision = {"announce": False, "reason": "unreachable", "warnings": ["hint-text"]}
    target = {
        "pubkey": "02lqwd",
        "address": "1.2.3.4:9735",
        "alias": "LQWD-Test",
        "region": "TEST",
    }
    with (
        patch("saturnzap.liquidity.lqwd.get_nearest", return_value=target),
        patch("saturnzap.node.connect_peer"),
        patch("saturnzap.node.decide_announce", return_value=decision),
        patch("saturnzap.node.open_channel", return_value="ucid_inbound"),
    ):
        result = liquidity.request_inbound(500_000)

    assert result["announce"] is False
    assert result["announce_reason"] == "unreachable"
    assert result["warnings"] == ["hint-text"]
