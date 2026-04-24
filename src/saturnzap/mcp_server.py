"""MCP Server — expose SaturnZap as tools for AI agents via stdio JSON-RPC."""

from __future__ import annotations

import functools
import os
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Lifespan — start/stop the LDK node once for the server's lifetime
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(server: FastMCP):  # noqa: ARG001
    """Start the LDK node on server boot, stop it on shutdown.

    If a daemon is already running with an IPC socket, skip the local
    node start — all calls will be routed through IPC transparently.
    """
    from saturnzap import keystore, node
    from saturnzap.ipc import daemon_is_running

    if daemon_is_running():
        # Daemon owns the node — MCP becomes a thin client via IPC.
        node._ipc_mode = True
    elif keystore.is_initialized():
        passphrase = keystore.get_passphrase()
        mnemonic = keystore.load_mnemonic(passphrase)
        node.start(mnemonic)
    yield
    node.stop()


mcp = FastMCP("saturnzap", lifespan=_lifespan)


def _tool(*args, **kwargs):
    """Wrap ``mcp.tool()`` so every tool catches ``CommandError`` / ``SystemExit``.

    Without this, ``output.error()`` raises ``CommandError`` (a ``SystemExit``
    subclass) which is a ``BaseException`` and escapes FastMCP's exception
    handler, terminating the MCP server. Convert to an error dict instead.
    """
    from saturnzap.output import CommandError

    decorator = mcp.tool(*args, **kwargs)

    def wrap(fn):
        @functools.wraps(fn)
        def safe(*a, **kw):
            try:
                return fn(*a, **kw)
            except CommandError as exc:
                return {
                    "status": "error",
                    "code": exc.error_code,
                    "message": exc.error_message,
                }
            except SystemExit as exc:
                return {
                    "status": "error",
                    "code": "COMMAND_ERROR",
                    "message": f"Command exited with code {exc.code}",
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "status": "error",
                    "code": "INTERNAL_ERROR",
                    "message": str(exc),
                }

        return decorator(safe)

    return wrap


# ---------------------------------------------------------------------------
# Lifecycle tools
# ---------------------------------------------------------------------------


@_tool()
def is_initialized() -> dict[str, Any]:
    """Check whether the SaturnZap wallet has been initialized."""
    from saturnzap import keystore

    return {"initialized": keystore.is_initialized()}


@_tool()
def init_wallet() -> dict[str, Any]:
    """Generate a new BIP39 seed and start the Lightning node.

    Only call this once. The passphrase must be set via SZ_PASSPHRASE env var.
    """
    from saturnzap import keystore, node

    if keystore.is_initialized():
        return {"status": "error", "code": "ALREADY_INITIALIZED",
                "message": "Wallet already initialized."}

    mnemonic = keystore.generate_mnemonic()
    passphrase = keystore.get_passphrase(confirm=True)
    path = keystore.save_encrypted(mnemonic, passphrase)
    n = node.start(mnemonic)

    return {
        "status": "ok",
        "mnemonic": mnemonic,
        "pubkey": n.node_id(),
        "seed_path": str(path),
        "message": "Wallet initialized. WRITE DOWN YOUR MNEMONIC AND STORE IT SAFELY.",
    }


@_tool()
def setup_wallet(
    auto: bool = True,
    region: str | None = None,
    inbound_sats: int = 100_000,
) -> dict[str, Any]:
    """Guided first-run: init wallet, generate address, optionally open channel.

    Idempotent — skips steps already complete. Preferred over init_wallet for agents.

    Args:
        auto: If True, also request inbound liquidity from LQWD.
        region: LQWD region code (e.g. CA, US, JP). Auto-selects nearest if omitted.
        inbound_sats: Inbound capacity to request in satoshis.
    """
    from saturnzap import keystore, node

    steps: list[dict] = []

    if keystore.is_initialized():
        passphrase = keystore.get_passphrase()
        mnemonic = keystore.load_mnemonic(passphrase)
        n = node.start(mnemonic)
        steps.append({"step": "init", "skipped": True, "reason": "already initialized"})
    else:
        mnemonic = keystore.generate_mnemonic()
        passphrase = keystore.get_passphrase(confirm=True)
        path = keystore.save_encrypted(mnemonic, passphrase)
        n = node.start(mnemonic)
        steps.append({
            "step": "init", "skipped": False,
            "mnemonic": mnemonic, "seed_path": str(path),
        })

    from saturnzap.config import get_network
    addr = node.new_onchain_address()
    network = get_network()
    steps.append({"step": "address", "address": addr, "network": network})

    if auto:
        from saturnzap import liquidity

        bal = node.get_balance()
        has_channels = len(bal["channels"]) > 0
        if has_channels:
            steps.append({"step": "inbound", "skipped": True,
                          "reason": "channel(s) already exist"})
        else:
            try:
                info = liquidity.request_inbound(inbound_sats, region)
                steps.append({"step": "inbound", "skipped": False, **info})
            except SystemExit:
                steps.append({"step": "inbound", "skipped": True,
                              "reason": "inbound request failed (fund wallet first)"})

    return {
        "status": "ok",
        "pubkey": n.node_id(),
        "steps": steps,
        "message": "Setup complete." if auto else
                   f"Setup complete. Fund wallet at: {addr}",
    }


@_tool()
def get_status() -> dict[str, Any]:
    """Return node pubkey, sync state, block height, and timestamps."""
    from saturnzap import node

    return node.get_status()


@_tool()
def get_connect_info(check: bool = False) -> dict[str, Any]:
    """Return node connection URI (pubkey@host:port) for sharing.

    Args:
        check: If True, test if the Lightning port is reachable from the internet.
    """
    from saturnzap import node

    info = node.get_connect_info()
    if check:
        info["reachable"] = node.check_port_reachable(
            host=info.get("host"), port=info.get("port"),
        )
    return info


@_tool()
def stop_node() -> dict[str, str]:
    """Stop the Lightning node gracefully."""
    from saturnzap import node

    node.stop()
    return {"status": "ok", "message": "Node stopped."}


# ---------------------------------------------------------------------------
# Wallet tools
# ---------------------------------------------------------------------------


@_tool()
def new_onchain_address() -> dict[str, str]:
    """Generate a new on-chain receive address (for funding the wallet)."""
    from saturnzap import node

    addr = node.new_onchain_address()
    from saturnzap.config import get_network
    return {"address": addr, "network": get_network()}


@_tool()
def get_balance() -> dict[str, Any]:
    """Return on-chain and Lightning balances with per-channel breakdown."""
    from saturnzap import node

    return node.get_balance()


@_tool()
def send_onchain(address: str, amount_sats: int | None = None) -> dict[str, Any]:
    """Send sats on-chain to an address.

    Args:
        address: Destination on-chain address.
        amount_sats: Amount in satoshis. If omitted, sends all funds.
    """
    from saturnzap import node

    txid = node.send_onchain(address, amount_sats)
    return {
        "status": "ok",
        "txid": txid,
        "amount_sats": amount_sats,
        "send_all": amount_sats is None,
    }


# ---------------------------------------------------------------------------
# Peer tools
# ---------------------------------------------------------------------------


@_tool()
def connect_peer(node_id: str, address: str) -> dict[str, str]:
    """Connect to a Lightning peer.

    Args:
        node_id: Peer's public key (hex).
        address: Peer's host:port (e.g. "1.2.3.4:9735").
    """
    from saturnzap import node

    node.connect_peer(node_id, address)
    return {"status": "ok", "node_id": node_id, "address": address,
            "message": "Peer added."}


@_tool()
def disconnect_peer(node_id: str) -> dict[str, str]:
    """Disconnect from a Lightning peer.

    Args:
        node_id: Peer's public key (hex).
    """
    from saturnzap import node

    node.disconnect_peer(node_id)
    return {"status": "ok", "node_id": node_id, "message": "Peer removed."}


@_tool()
def list_peers() -> dict[str, Any]:
    """List all connected and persisted peers."""
    from saturnzap import node

    return {"peers": node.list_peers()}


# ---------------------------------------------------------------------------
# Channel tools
# ---------------------------------------------------------------------------


@_tool()
def list_channels() -> dict[str, Any]:
    """List all Lightning channels with capacity and readiness info."""
    from saturnzap import node

    return {"channels": node.list_channels()}


@_tool()
def open_channel(
    node_id: str,
    address: str,
    amount_sats: int,
    announce: bool | None = None,
) -> dict[str, Any]:
    """Open a Lightning channel to a peer.

    Args:
        node_id: Peer's public key (hex).
        address: Peer's host:port.
        amount_sats: Channel capacity in satoshis.
        announce: Whether to announce the channel to the network.
            ``None`` (default) uses the auto gate: announce iff the node
            is reachable from the internet (mainnet only). ``True`` /
            ``False`` are explicit overrides.
    """
    from saturnzap import node

    decision = node.decide_announce(announce)
    ucid = node.open_channel(
        node_id, address, amount_sats, announce=decision["announce"],
    )
    response: dict[str, Any] = {
        "status": "ok",
        "user_channel_id": ucid,
        "counterparty": node_id,
        "amount_sats": amount_sats,
        "announce": decision["announce"],
        "announce_reason": decision["reason"],
        "message": "Channel open initiated.",
    }
    if decision["warnings"]:
        response["warnings"] = decision["warnings"]
    return response


@_tool()
def close_channel(
    channel_id: str,
    counterparty_node_id: str,
    force: bool = False,
) -> dict[str, str]:
    """Close a Lightning channel.

    Args:
        channel_id: The channel ID to close.
        counterparty_node_id: Counterparty's public key.
        force: If True, force-close instead of cooperative close.
    """
    from saturnzap import node

    if force:
        node.force_close_channel(channel_id, counterparty_node_id)
        return {"status": "ok", "channel_id": channel_id,
                "message": "Force-close initiated."}
    node.close_channel(channel_id, counterparty_node_id)
    return {"status": "ok", "channel_id": channel_id,
            "message": "Cooperative close initiated."}


# ---------------------------------------------------------------------------
# Payment tools
# ---------------------------------------------------------------------------


@_tool()
def create_invoice(
    amount_sats: int = 0,
    memo: str = "",
    expiry_secs: int = 3600,
) -> dict[str, Any]:
    """Create a BOLT11 invoice to receive a Lightning payment.

    Args:
        amount_sats: Amount in satoshis. 0 for variable-amount invoice.
        memo: Description to attach to the invoice.
        expiry_secs: Invoice expiry in seconds (default 3600).
    """
    from saturnzap import payments

    if amount_sats > 0:
        return payments.create_invoice(amount_sats, memo, expiry_secs)
    return payments.create_variable_invoice(memo, expiry_secs)


@_tool()
def pay_invoice(invoice: str, max_sats: int | None = None) -> dict[str, Any]:
    """Pay a BOLT11 Lightning invoice.

    Args:
        invoice: The BOLT11 invoice string.
        max_sats: Optional spending cap in sats. Rejects if invoice exceeds this.
    """
    from saturnzap import payments

    return payments.pay_invoice(invoice, max_sats)


@_tool()
def keysend(pubkey: str, amount_sats: int) -> dict[str, Any]:
    """Send a spontaneous keysend payment.

    Args:
        pubkey: Destination node's public key (hex).
        amount_sats: Amount to send in satoshis.
    """
    from saturnzap import payments

    return payments.keysend(pubkey, amount_sats)


@_tool()
def list_transactions(limit: int = 20) -> dict[str, Any]:
    """List recent payment history.

    Args:
        limit: Maximum number of transactions to return (default 20).
    """
    from saturnzap import payments

    txns = payments.list_transactions(limit)
    return {"transactions": txns, "count": len(txns)}


# ---------------------------------------------------------------------------
# L402 tools
# ---------------------------------------------------------------------------


@_tool()
def l402_fetch(
    url: str,
    method: str = "GET",
    body: str | None = None,
    max_sats: int | None = None,
) -> dict[str, Any]:
    """Fetch a URL with L402 auto-pay. If HTTP 402 is returned, pays the
    Lightning invoice and retries with the token.

    Args:
        url: The URL to fetch.
        method: HTTP method (GET, POST, etc.).
        body: Optional request body.
        max_sats: Maximum sats to spend. Rejects if invoice exceeds this.
    """
    import json as _json

    from saturnzap import l402

    # Apply server-level spending cap from env
    env_cap = os.environ.get("SZ_MCP_MAX_SPEND_SATS")
    if env_cap and max_sats is None:
        max_sats = int(env_cap)

    result = l402.fetch(url, method=method, body=body, max_sats=max_sats)

    resp: dict[str, Any] = {
        "url": result.url,
        "http_status": result.http_status,
    }
    if result.payment_hash:
        resp["payment_hash"] = result.payment_hash
        resp["amount_sats"] = result.amount_sats
        resp["fee_sats"] = result.fee_sats
    resp["duration_ms"] = result.duration_ms

    try:
        resp["body"] = _json.loads(result.body)
    except (ValueError, _json.JSONDecodeError):
        resp["body"] = result.body

    if result.warnings:
        resp["warnings"] = result.warnings

    return resp


# ---------------------------------------------------------------------------
# Liquidity tools
# ---------------------------------------------------------------------------


@_tool()
def liquidity_status() -> dict[str, Any]:
    """Return channel health scores and actionable recommendations."""
    from saturnzap import liquidity

    return liquidity.get_status()


@_tool()
def request_inbound(
    amount_sats: int,
    region: str | None = None,
) -> dict[str, Any]:
    """Request inbound liquidity from an LQWD node.

    Args:
        amount_sats: Desired inbound capacity in satoshis.
        region: Optional LQWD region code (e.g. CA, US, JP).
            Auto-selects nearest if omitted.
    """
    from saturnzap import liquidity

    return liquidity.request_inbound(amount_sats, region)


@_tool()
def list_lqwd_nodes(region: str | None = None) -> dict[str, Any]:
    """List available LQWD Lightning nodes.

    Args:
        region: Optional region code to filter (e.g. CA, US, JP).
    """
    from saturnzap import lqwd

    nodes = lqwd.list_nodes(region)
    return {"nodes": nodes, "count": len(nodes)}


# ---------------------------------------------------------------------------
# Backup & Restore tools
# ---------------------------------------------------------------------------


@_tool()
def backup_wallet(output_path: str = "saturnzap-backup.json") -> dict[str, Any]:
    """Create an encrypted backup of the wallet.

    Args:
        output_path: Path to write the encrypted backup file.
    """
    from pathlib import Path

    from saturnzap import backup, keystore

    passphrase = keystore.get_passphrase()
    return backup.backup(Path(output_path), passphrase)


@_tool()
def restore_wallet(input_path: str) -> dict[str, Any]:
    """Restore the wallet from an encrypted backup.

    Args:
        input_path: Path to the encrypted backup file.
    """
    from pathlib import Path

    from saturnzap import backup, keystore

    passphrase = keystore.get_passphrase(confirm=True)
    return backup.restore(Path(input_path), passphrase)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def serve() -> None:
    """Run the MCP server on stdio transport."""
    mcp.run(transport="stdio")
