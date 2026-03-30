"""Shared fixtures for integration tests.

Integration tests use the real CLI (CliRunner) with mocked LDK node,
exercising multi-command flows end-to-end.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("SZ_PASSPHRASE", "integration-test")


@pytest.fixture()
def mock_node():
    """Full-featured mock LDK Node for integration flows."""
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
    n.onchain_payment.return_value.new_address.return_value = "tb1qintegration"
    n.onchain_payment.return_value.send_to_address.return_value = "txid_int"
    n.status.return_value = SimpleNamespace(
        is_running=True,
        current_best_block=SimpleNamespace(height=12345, block_hash="00ff"),
        latest_onchain_wallet_sync_timestamp=1000,
        latest_lightning_wallet_sync_timestamp=1000,
    )
    return n
