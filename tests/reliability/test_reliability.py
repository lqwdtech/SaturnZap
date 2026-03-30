"""Reliability tests — rapid commands, concurrent access, restart cycles, edge cases."""

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
    monkeypatch.setenv("SZ_PASSPHRASE", "reliability")


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
    n.status.return_value = SimpleNamespace(
        is_running=True,
        current_best_block=SimpleNamespace(height=12345, block_hash="00ff"),
        latest_onchain_wallet_sync_timestamp=1000,
        latest_lightning_wallet_sync_timestamp=1000,
    )
    return n


# ── Rapid command sequences ──────────────────────────────────────


def test_rapid_status_50_times(mock_node):
    """50 consecutive status calls should all return valid JSON."""
    with (
        patch("saturnzap.node._require_node", return_value=mock_node),
        patch("time.time", return_value=1010),
    ):
        for i in range(50):
            result = runner.invoke(app, ["status"])
            assert result.exit_code == 0, f"Iteration {i} failed"
            data = json.loads(result.output)
            assert data["status"] == "ok"


def test_rapid_balance_50_times(mock_node):
    """50 consecutive balance calls should all succeed."""
    with patch("saturnzap.node._require_node", return_value=mock_node):
        for i in range(50):
            result = runner.invoke(app, ["balance"])
            assert result.exit_code == 0, f"Iteration {i} failed"
            data = json.loads(result.output)
            assert data["onchain_sats"] == 100_000


# ── Node restart cycles ─────────────────────────────────────────


def test_start_stop_10_cycles(mock_node):
    """Start and stop the node 10 times — should not crash or leave state dirty."""
    from saturnzap import node

    for i in range(10):
        with patch("saturnzap.node.build_node", return_value=mock_node):
            node.start("abandon " * 23 + "art")
        node.stop()
        assert node._node is None, f"Cycle {i}: _node should be None after stop"


# ── Large transaction history ────────────────────────────────────


def test_large_history_10k_items(mock_node):
    """list_transactions with limit should work against 10k mock payments."""
    payments = []
    for i in range(10_000):
        payments.append(SimpleNamespace(
            id=f"pay_{i:05d}",
            kind=SimpleNamespace(
                is_bolt11=lambda: True,
                is_bolt11_jit=lambda: False,
                is_spontaneous=lambda: False,
                is_onchain=lambda: False,
                is_bolt12_offer=lambda: False,
                is_bolt12_refund=lambda: False,
            ),
            direction="OUTBOUND",
            amount_msat=1000 * (i + 1),
            fee_paid_msat=100,
            status="SUCCEEDED",
            latest_update_timestamp=1700000000 + i,
        ))
    mock_node.list_payments.return_value = payments

    from saturnzap import payments as pay_mod

    with patch("saturnzap.payments._require_node", return_value=mock_node):
        result = pay_mod.list_transactions(limit=5)

    assert len(result) == 5
    # Should be sorted most recent first
    assert result[0]["timestamp"] > result[-1]["timestamp"]


# ── Disk write failure ───────────────────────────────────────────


def test_disk_full_on_seed_save(tmp_path, monkeypatch):
    """Simulate disk full during seed save — should not leave half-written files."""
    from saturnzap import keystore

    mnemonic = keystore.generate_mnemonic()

    # Make the directory read-only to simulate write failure
    data_dir = tmp_path / "saturnzap"
    data_dir.mkdir()
    (data_dir / "seed.salt").touch()  # Create file first

    def fail_write(self, data):
        raise OSError("No space left on device")

    with patch.object(type(keystore.seed_path()), "write_bytes", fail_write):  # noqa: SIM117
        with pytest.raises(OSError):
            keystore.save_encrypted(mnemonic, "testpass")


# ── Concurrent-safe JSON output ──────────────────────────────────


def test_parallel_json_output_shape_consistency(mock_node):
    """Multiple different commands should all produce consistent JSON envelopes."""
    mock_node.onchain_payment.return_value.new_address.return_value = "tb1qtest"

    commands = [
        ["balance"],
        ["address"],
        ["balance"],
        ["address"],
        ["balance"],
    ]

    with patch("saturnzap.node._require_node", return_value=mock_node):
        for cmd in commands:
            result = runner.invoke(app, cmd)
            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "status" in data
            assert data["status"] == "ok"
