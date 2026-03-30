"""Tests for saturnzap.node — LDK node lifecycle, balance, channels, peers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from saturnzap import node


@pytest.fixture(autouse=True)
def _clean_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


@pytest.fixture(autouse=True)
def _reset_node():
    """Ensure module-level _node is None between tests."""
    node._node = None
    yield
    node._node = None


@pytest.fixture()
def mock_ldk_node():
    """A MagicMock behaving like an LDK Node."""
    n = MagicMock()
    n.node_id.return_value = "02abc123"
    n.status.return_value = SimpleNamespace(
        is_running=True,
        current_best_block=SimpleNamespace(height=100, block_hash="00ff"),
        latest_onchain_wallet_sync_timestamp=1000,
        latest_lightning_wallet_sync_timestamp=1000,
    )
    n.list_peers.return_value = []
    n.list_channels.return_value = []
    n.list_balances.return_value = SimpleNamespace(
        total_onchain_balance_sats=100_000,
        spendable_onchain_balance_sats=90_000,
        total_lightning_balance_sats=50_000,
        total_anchor_channels_reserve_sats=0,
    )
    n.list_payments.return_value = []
    return n


# ── build_node ───────────────────────────────────────────────────


def test_build_node_returns_node():
    """build_node should call Builder methods and return a node."""
    mock_builder = MagicMock()
    mock_built = MagicMock()
    mock_builder.build.return_value = mock_built

    with (
        patch("saturnzap.node.load_config", return_value={"network": "signet"}),
        patch("saturnzap.node.resolve_esplora", return_value="https://esplora.test"),
        patch("saturnzap.node.default_config", return_value=MagicMock()),
        patch("saturnzap.node.Builder") as MockBuilder,
    ):
        MockBuilder.from_config.return_value = mock_builder
        result = node.build_node("abandon " * 23 + "art")

    assert result is mock_built
    mock_builder.set_network.assert_called_once()
    mock_builder.set_chain_source_esplora.assert_called_once()
    mock_builder.set_entropy_bip39_mnemonic.assert_called_once()
    mock_builder.set_gossip_source_p2p.assert_called_once()


# ── start / stop / get_node ──────────────────────────────────────


def test_start_caches_node(tmp_path, mock_ldk_node):
    with patch("saturnzap.node.build_node", return_value=mock_ldk_node):
        result = node.start("mnemonic words")

    assert result is mock_ldk_node
    assert node.get_node() is mock_ldk_node
    mock_ldk_node.start.assert_called_once()


def test_start_idempotent(mock_ldk_node):
    node._node = mock_ldk_node
    result = node.start("mnemonic words")
    assert result is mock_ldk_node
    # Should NOT call build_node again
    mock_ldk_node.start.assert_not_called()


def test_stop_clears_node(tmp_path, mock_ldk_node):
    node._node = mock_ldk_node
    # Create the flag file
    from saturnzap.config import data_dir
    d = data_dir()
    (d / "node.active").write_text("02abc123")

    node.stop()

    assert node.get_node() is None
    mock_ldk_node.stop.assert_called_once()
    assert not (d / "node.active").exists()


def test_stop_without_node(tmp_path):
    """stop() when no node is running should not crash."""
    node.stop()  # Should be a no-op


def test_get_node_returns_none_initially():
    assert node.get_node() is None


# ── _require_node ────────────────────────────────────────────────


def test_require_node_returns_cached(mock_ldk_node):
    node._node = mock_ldk_node
    result = node._require_node()
    assert result is mock_ldk_node


def test_require_node_errors_no_seed():
    """_require_node raises SystemExit if no seed file exists."""
    with pytest.raises(SystemExit):
        node._require_node()


def test_require_node_auto_starts(tmp_path, monkeypatch, mock_ldk_node):
    """_require_node auto-starts from encrypted seed when not cached."""
    monkeypatch.setenv("SZ_PASSPHRASE", "testpass")
    from saturnzap import keystore
    keystore.save_encrypted("abandon " * 23 + "art", "testpass")

    with patch("saturnzap.node.start", return_value=mock_ldk_node) as mock_start:
        result = node._require_node()

    assert result is mock_ldk_node
    mock_start.assert_called_once()


# ── get_status ───────────────────────────────────────────────────


def test_get_status_returns_all_fields(mock_ldk_node):
    node._node = mock_ldk_node

    with (
        patch("saturnzap.node._require_node", return_value=mock_ldk_node),
        patch("time.time", return_value=1010),
    ):
        result = node.get_status()

    assert result["pubkey"] == "02abc123"
    assert result["is_running"] is True
    assert result["block_height"] == 100
    assert result["peer_count"] == 0
    assert result["channel_count"] == 0
    assert result["usable_channel_count"] == 0
    assert result["sync_lag_seconds"] == 10  # 1010 - 1000


def test_get_status_sync_lag_none_when_no_timestamp(mock_ldk_node):
    mock_ldk_node.status.return_value.latest_onchain_wallet_sync_timestamp = None
    node._node = mock_ldk_node

    with (
        patch("saturnzap.node._require_node", return_value=mock_ldk_node),
        patch("time.time", return_value=1010),
    ):
        result = node.get_status()

    assert result["sync_lag_seconds"] is None


# ── new_onchain_address ──────────────────────────────────────────


def test_new_onchain_address(mock_ldk_node):
    mock_ldk_node.onchain_payment.return_value.new_address.return_value = "tb1qtest..."
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        result = node.new_onchain_address()

    assert result == "tb1qtest..."


# ── send_onchain ─────────────────────────────────────────────────


def test_send_onchain_success(mock_ldk_node):
    mock_ldk_node.onchain_payment.return_value.send_to_address.return_value = "txid123"
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        result = node.send_onchain("tb1qdest...", 10_000)

    assert result == "txid123"


def test_send_onchain_send_all(mock_ldk_node):
    result = mock_ldk_node.onchain_payment.return_value
    result.send_all_to_address.return_value = "txidall"
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        result = node.send_onchain("tb1qdest...", None)

    assert result == "txidall"
    mock_ldk_node.onchain_payment.return_value.send_all_to_address.assert_called_once()


def test_send_onchain_insufficient_funds(mock_ldk_node):
    mock_ldk_node.list_balances.return_value.spendable_onchain_balance_sats = 5_000
    node._node = mock_ldk_node

    with (
        patch("saturnzap.node._require_node", return_value=mock_ldk_node),
        pytest.raises(SystemExit),
    ):
        node.send_onchain("tb1qdest...", 10_000)


def test_send_onchain_send_all_zero_balance(mock_ldk_node):
    mock_ldk_node.list_balances.return_value.spendable_onchain_balance_sats = 0
    node._node = mock_ldk_node

    with (
        patch("saturnzap.node._require_node", return_value=mock_ldk_node),
        pytest.raises(SystemExit),
    ):
        node.send_onchain("tb1qdest...", None)


# ── get_balance ──────────────────────────────────────────────────


def test_get_balance_returns_dict(mock_ldk_node):
    mock_ldk_node.list_channels.return_value = []
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        result = node.get_balance()

    assert result["onchain_sats"] == 100_000
    assert result["spendable_onchain_sats"] == 90_000
    assert result["lightning_sats"] == 50_000
    assert result["anchor_reserve_sats"] == 0
    assert result["channels"] == []


# ── list_peers ───────────────────────────────────────────────────


def test_list_peers(mock_ldk_node):
    mock_ldk_node.list_peers.return_value = [
        SimpleNamespace(
            node_id="02peer1", address="1.2.3.4:9735",
            is_connected=True, is_persisted=True,
        ),
    ]
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        result = node.list_peers()

    assert len(result) == 1
    assert result[0]["node_id"] == "02peer1"
    assert result[0]["is_connected"] is True


# ── _channel_to_dict ─────────────────────────────────────────────


def _make_channel(is_usable, is_ready, **kwargs):
    defaults = {
        "channel_id": "ch001",
        "counterparty_node_id": "02peer",
        "channel_value_sats": 100_000,
        "outbound_capacity_msat": 50_000_000,
        "inbound_capacity_msat": 50_000_000,
        "is_channel_ready": is_ready,
        "is_usable": is_usable,
        "is_outbound": True,
        "is_announced": False,
        "confirmations": 6,
        "funding_txo": "txo:0",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_channel_to_dict_ready():
    ch = _make_channel(is_usable=True, is_ready=True)
    d = node._channel_to_dict(ch)
    assert d["status_reason"] == "ready"
    assert d["is_usable"] is True


def test_channel_to_dict_awaiting():
    ch = _make_channel(is_usable=False, is_ready=False)
    d = node._channel_to_dict(ch)
    assert d["status_reason"] == "awaiting_confirmation"


def test_channel_to_dict_peer_offline():
    ch = _make_channel(is_usable=False, is_ready=True)
    d = node._channel_to_dict(ch)
    assert d["status_reason"] == "peer_offline"


# ── list_channels ────────────────────────────────────────────────


def test_list_channels(mock_ldk_node):
    mock_ldk_node.list_channels.return_value = [
        _make_channel(is_usable=True, is_ready=True),
    ]
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        result = node.list_channels()

    assert len(result) == 1
    assert result[0]["channel_id"] == "ch001"


# ── open_channel ─────────────────────────────────────────────────


def test_open_channel(mock_ldk_node):
    mock_ldk_node.open_channel.return_value = "ucid001"
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        result = node.open_channel("02peer", "1.2.3.4:9735", 100_000)

    assert result == "ucid001"


def test_open_announced_channel(mock_ldk_node):
    mock_ldk_node.open_announced_channel.return_value = "ucid002"
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        result = node.open_channel("02peer", "1.2.3.4:9735", 100_000, announce=True)

    assert result == "ucid002"


# ── close_channel / force_close ──────────────────────────────────


def test_close_channel(mock_ldk_node):
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        node.close_channel("ch001", "02peer")

    mock_ldk_node.close_channel.assert_called_once_with("ch001", "02peer")


def test_force_close_channel(mock_ldk_node):
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        node.force_close_channel("ch001", "02peer", reason="test")

    mock_ldk_node.force_close_channel.assert_called_once_with("ch001", "02peer", "test")


# ── connect_peer / disconnect_peer ───────────────────────────────


def test_connect_peer(mock_ldk_node):
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        node.connect_peer("02peer", "1.2.3.4:9735")

    mock_ldk_node.connect.assert_called_once_with("02peer", "1.2.3.4:9735", True)


def test_disconnect_peer(mock_ldk_node):
    node._node = mock_ldk_node

    with patch("saturnzap.node._require_node", return_value=mock_ldk_node):
        node.disconnect_peer("02peer")

    mock_ldk_node.disconnect.assert_called_once_with("02peer")


# ── wait_channel_ready ───────────────────────────────────────────


def test_wait_channel_ready_immediate(mock_ldk_node):
    mock_ldk_node.list_channels.return_value = [
        _make_channel(is_usable=True, is_ready=True),
    ]
    node._node = mock_ldk_node

    with (
        patch("saturnzap.node._require_node", return_value=mock_ldk_node),
        patch("time.sleep"),
    ):
        result = node.wait_channel_ready(timeout=10)

    assert result["status"] == "ready"
    assert result["channel"]["channel_id"] == "ch001"


def test_wait_channel_ready_specific_channel(mock_ldk_node):
    mock_ldk_node.list_channels.return_value = [
        _make_channel(is_usable=True, is_ready=True, channel_id="target"),
    ]
    node._node = mock_ldk_node

    with (
        patch("saturnzap.node._require_node", return_value=mock_ldk_node),
        patch("time.sleep"),
    ):
        result = node.wait_channel_ready(channel_id="target", timeout=10)

    assert result["status"] == "ready"


def test_wait_channel_ready_timeout(mock_ldk_node):
    mock_ldk_node.list_channels.return_value = [
        _make_channel(is_usable=False, is_ready=False),
    ]
    node._node = mock_ldk_node

    with (
        patch("saturnzap.node._require_node", return_value=mock_ldk_node),
        patch("time.sleep"),
        patch("time.monotonic", side_effect=[0, 0, 11]),
    ):
        result = node.wait_channel_ready(timeout=10)

    assert result["status"] == "timeout"
    assert result["waited_seconds"] == 10


# ── _network_from_str ────────────────────────────────────────────


def test_network_from_str_signet():
    from ldk_node import Network
    assert node._network_from_str("signet") == Network.SIGNET


def test_network_from_str_testnet():
    from ldk_node import Network
    assert node._network_from_str("testnet") == Network.TESTNET


def test_network_from_str_bitcoin():
    from ldk_node import Network
    assert node._network_from_str("bitcoin") == Network.BITCOIN


def test_network_from_str_invalid():
    with pytest.raises(KeyError):
        node._network_from_str("invalid")
