"""LDK Node lifecycle — build, start, stop, status, peers, channels."""

from __future__ import annotations

from ldk_node import Builder, Network, Node, default_config

from saturnzap.config import data_dir, load_config

_node: Node | None = None

# File that records whether the node should be running (simple PID-less flag)
_RUNNING_FLAG = "node.active"


def _node_storage() -> str:
    """Return the LDK Node storage directory path as a string."""
    p = data_dir() / "ldk"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def _network_from_str(name: str) -> Network:
    return {
        "signet": Network.SIGNET,
        "testnet": Network.TESTNET,
        "regtest": Network.REGTEST,
        "bitcoin": Network.BITCOIN,
    }[name]


def build_node(mnemonic: str) -> Node:
    """Configure and build an LDK Node instance (does not start it)."""
    cfg = load_config()
    network = _network_from_str(cfg.get("network", "signet"))
    esplora_url = cfg.get("esplora_url", "https://mempool.space/signet/api")

    config = default_config()
    builder = Builder.from_config(config)
    builder.set_network(network)
    builder.set_storage_dir_path(_node_storage())
    builder.set_chain_source_esplora(esplora_url, None)
    builder.set_entropy_bip39_mnemonic(mnemonic, None)
    builder.set_listening_addresses(["0.0.0.0:9735"])
    builder.set_gossip_source_p2p()

    return builder.build()


def start(mnemonic: str) -> Node:
    """Build, start, and return the running node. Caches in module state."""
    global _node
    if _node is not None:
        return _node

    node = build_node(mnemonic)
    node.start()
    # Write a flag file so status can detect a "should be running" state
    (data_dir() / _RUNNING_FLAG).write_text(node.node_id())
    _node = node
    return node


def stop() -> None:
    """Stop the running node and clear the flag."""
    global _node
    flag = data_dir() / _RUNNING_FLAG
    if _node is not None:
        _node.stop()
        _node = None
    if flag.exists():
        flag.unlink()


def get_node() -> Node | None:
    """Return the cached node if running, else None."""
    return _node


def get_status() -> dict:
    """Return a JSON-serialisable status dict."""
    node = _require_node()
    node.sync_wallets()
    st = node.status()
    return {
        "pubkey": node.node_id(),
        "is_running": st.is_running,
        "network": load_config().get("network", "signet"),
        "block_height": st.current_best_block.height,
        "block_hash": st.current_best_block.block_hash,
        "latest_wallet_sync": st.latest_onchain_wallet_sync_timestamp,
        "latest_lightning_sync": st.latest_lightning_wallet_sync_timestamp,
    }


# ── Helpers ──────────────────────────────────────────────────────


def _require_node() -> Node:
    """Return the running node, auto-starting it from the stored seed if needed."""
    global _node
    if _node is not None:
        return _node

    from saturnzap import keystore, output

    if not keystore.is_initialized():
        output.error("NO_SEED", "No seed found. Run 'sz init' first.", exit_code=1)

    passphrase = keystore.get_passphrase()
    mnemonic = keystore.load_mnemonic(passphrase)
    _node = start(mnemonic)
    return _node


# ── Address / Balance ────────────────────────────────────────────


def new_onchain_address() -> str:
    """Generate a new on-chain (signet) receive address."""
    return _require_node().onchain_payment().new_address()


def get_balance() -> dict:
    """Return on-chain and lightning balances."""
    node = _require_node()
    node.sync_wallets()
    bal = node.list_balances()
    channels = [_channel_to_dict(c) for c in node.list_channels()]
    return {
        "onchain_sats": bal.total_onchain_balance_sats,
        "spendable_onchain_sats": bal.spendable_onchain_balance_sats,
        "lightning_sats": bal.total_lightning_balance_sats,
        "anchor_reserve_sats": bal.total_anchor_channels_reserve_sats,
        "channels": channels,
    }


# ── Peers ────────────────────────────────────────────────────────


def connect_peer(node_id: str, address: str, persist: bool = True) -> None:
    """Connect to a peer by pubkey and address (host:port)."""
    _require_node().connect(node_id, address, persist)


def disconnect_peer(node_id: str) -> None:
    """Disconnect from a peer."""
    _require_node().disconnect(node_id)


def list_peers() -> list[dict]:
    """Return list of peers as dicts."""
    return [
        {
            "node_id": p.node_id,
            "address": p.address,
            "is_connected": p.is_connected,
            "is_persisted": p.is_persisted,
        }
        for p in _require_node().list_peers()
    ]


# ── Channels ─────────────────────────────────────────────────────


def _channel_to_dict(c) -> dict:
    """Convert a ChannelDetails to a JSON-serialisable dict."""
    return {
        "channel_id": str(c.channel_id),
        "counterparty_node_id": c.counterparty_node_id,
        "channel_value_sats": c.channel_value_sats,
        "outbound_capacity_msat": c.outbound_capacity_msat,
        "inbound_capacity_msat": c.inbound_capacity_msat,
        "is_channel_ready": c.is_channel_ready,
        "is_usable": c.is_usable,
        "is_outbound": c.is_outbound,
        "is_announced": c.is_announced,
        "confirmations": c.confirmations,
        "funding_txo": str(c.funding_txo) if c.funding_txo else None,
    }


def list_channels() -> list[dict]:
    """Return all channels as dicts."""
    return [_channel_to_dict(c) for c in _require_node().list_channels()]


def open_channel(
    node_id: str,
    address: str,
    amount_sats: int,
    *,
    push_msat: int | None = None,
    announce: bool = False,
) -> str:
    """Open a channel to a peer. Returns the user_channel_id."""
    node = _require_node()
    if announce:
        ucid = node.open_announced_channel(
            node_id, address, amount_sats, push_msat, None,
        )
    else:
        ucid = node.open_channel(
            node_id, address, amount_sats, push_msat, None,
        )
    return str(ucid)


def close_channel(channel_id: str, counterparty_node_id: str) -> None:
    """Cooperatively close a channel."""
    _require_node().close_channel(channel_id, counterparty_node_id)


def force_close_channel(
    channel_id: str, counterparty_node_id: str, reason: str | None = None,
) -> None:
    """Force-close a channel."""
    _require_node().force_close_channel(channel_id, counterparty_node_id, reason)
