"""SaturnZap CLI — ``sz`` command tree."""

from __future__ import annotations

import os
from typing import Annotated

import typer
from dotenv import load_dotenv

from saturnzap import output

load_dotenv()  # reads .env into os.environ early


_LDK_ERROR_MAP: dict[str, tuple[str, int]] = {
    "ConnectionFailed": ("CONNECTION_FAILED", 1),
    "InsufficientFunds": ("INSUFFICIENT_FUNDS", 1),
    "InvalidPublicKey": ("INVALID_PUBKEY", 1),
    "InvalidAddress": ("INVALID_ADDRESS", 1),
    "InvalidInvoice": ("INVALID_INVOICE", 1),
    "InvalidChannelId": ("INVALID_CHANNEL_ID", 1),
    "InvalidNetwork": ("INVALID_NETWORK", 1),
    "PaymentFailed": ("PAYMENT_FAILED", 1),
    "ChannelCreationFailed": ("CHANNEL_CREATION_FAILED", 1),
}


def main_cli() -> None:
    """Entry point that wraps the Typer app with LDK error handling."""
    try:
        import ldk_node as _  # noqa: F401
    except ImportError:
        import sys

        print(
            "error: ldk-node is not installed.\n"
            "Install it from the vendored wheel:\n"
            "  pip install vendor/ldk_node-0.7.0-py3-none-any.whl\n"
            "Or with --find-links from GitHub Releases:\n"
            "  pip install saturnzap --find-links "
            "https://github.com/ShoneAnstey/SaturnZap/releases/latest/download/",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    try:
        app()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        exc_type = type(exc).__name__
        exc_detail = str(exc)
        # Check if it's an LDK NodeError variant
        for variant, (code, exit_code) in _LDK_ERROR_MAP.items():
            if variant in exc_type or variant in exc_detail:
                output.error(code, exc_detail, exit_code=exit_code)
        # Fallback for any other LDK / unexpected errors
        if "ldk_node" in type(exc).__module__:
            output.error("LDK_ERROR", exc_detail, exit_code=1)
        output.error("INTERNAL_ERROR", exc_detail, exit_code=1)

app = typer.Typer(
    name="sz",
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


@app.callback()
def main(
    pretty: Annotated[
        bool,
        typer.Option("--pretty", help="Pretty-print JSON output."),
    ] = False,
) -> None:
    """SaturnZap — Lightning wallet for autonomous AI agents."""
    if pretty or os.environ.get("SZ_PRETTY", "") == "1":
        output.set_pretty(True)


# ── Phase 1 commands ─────────────────────────────────────────────


@app.command()
def init() -> None:
    """Generate seed, start node, peer with nearest LQWD node."""
    from saturnzap import keystore
    from saturnzap import node as node_mod

    if keystore.is_initialized():
        output.error("ALREADY_INITIALIZED", "Wallet already initialized. Seed exists.")

    mnemonic = keystore.generate_mnemonic()
    passphrase = keystore.get_passphrase(confirm=True)
    path = keystore.save_encrypted(mnemonic, passphrase)

    # Start the node with the fresh mnemonic
    n = node_mod.start(mnemonic)

    output.ok(
        mnemonic=mnemonic,
        pubkey=n.node_id(),
        seed_path=str(path),
        message="Wallet initialized. WRITE DOWN YOUR MNEMONIC AND STORE IT SAFELY.",
    )


@app.command()
def start() -> None:
    """Start the Lightning node, verify connectivity, and exit."""
    from saturnzap import node as node_mod

    n = node_mod._require_node()
    output.ok(pubkey=n.node_id(), message="Node started.")


@app.command()
def stop() -> None:
    """Stop the Lightning node and clean up."""
    from saturnzap import node as node_mod

    node_mod.stop()
    output.ok(message="Node stopped.")


@app.command()
def status() -> None:
    """Show node pubkey, sync state, and uptime."""
    from saturnzap import node as node_mod

    info = node_mod.get_status()
    output.ok(**info)


@app.command()
def address() -> None:
    """Generate a new on-chain receive address (for faucet deposits)."""
    from saturnzap import node as node_mod

    addr = node_mod.new_onchain_address()
    output.ok(address=addr, network=node_mod.load_config().get("network", "signet"))


@app.command()
def balance() -> None:
    """Show on-chain and lightning balances with per-channel breakdown."""
    from saturnzap import node as node_mod

    info = node_mod.get_balance()
    output.ok(**info)


# ── Phase 3: Payments ────────────────────────────────────────────


@app.command()
def invoice(
    amount_sats: Annotated[
        int,
        typer.Option("--amount-sats", help="Invoice amount in sats"),
    ] = 0,
    memo: Annotated[
        str,
        typer.Option("--memo", help="Invoice description"),
    ] = "",
    expiry: Annotated[
        int,
        typer.Option("--expiry", help="Invoice expiry in seconds"),
    ] = 3600,
) -> None:
    """Create a BOLT11 invoice to receive a payment."""
    from saturnzap import payments

    if amount_sats > 0:
        info = payments.create_invoice(amount_sats, memo, expiry)
    else:
        info = payments.create_variable_invoice(memo, expiry)
    output.ok(**info)


@app.command()
def pay(
    invoice_str: Annotated[
        str,
        typer.Option("--invoice", help="BOLT11 invoice string"),
    ],
    max_sats: Annotated[
        int | None,
        typer.Option("--max-sats", help="Spending cap in sats"),
    ] = None,
) -> None:
    """Pay a BOLT11 invoice."""
    from saturnzap import payments

    info = payments.pay_invoice(invoice_str, max_sats)
    output.ok(**info, message="Payment sent.")


@app.command()
def keysend(
    pubkey: Annotated[
        str,
        typer.Option("--pubkey", help="Destination node public key"),
    ],
    amount_sats: Annotated[
        int,
        typer.Option("--amount-sats", help="Amount to send in sats"),
    ],
) -> None:
    """Send a spontaneous keysend payment."""
    from saturnzap import payments

    info = payments.keysend(pubkey, amount_sats)
    output.ok(**info, message="Keysend sent.")


@app.command()
def transactions(
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max number of transactions to show"),
    ] = 20,
) -> None:
    """Show payment history."""
    from saturnzap import payments

    txns = payments.list_transactions(limit)
    output.ok(transactions=txns, count=len(txns))


# ── Phase 2: Peers ───────────────────────────────────────────────

peers_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
app.add_typer(peers_app, name="peers", help="Manage Lightning peers.")


@peers_app.command("list")
def peers_list() -> None:
    """List connected and persisted peers."""
    from saturnzap import node as node_mod

    output.ok(peers=node_mod.list_peers())


@peers_app.command("add")
def peers_add(
    target: Annotated[
        str,
        typer.Argument(help="Peer address as <pubkey>@<host>:<port>"),
    ],
) -> None:
    """Connect to a peer."""
    from saturnzap import node as node_mod

    node_id, address = _parse_peer_address(target)
    node_mod.connect_peer(node_id, address)
    output.ok(node_id=node_id, address=address, message="Peer added.")


@peers_app.command("remove")
def peers_remove(
    pubkey: Annotated[str, typer.Argument(help="Peer public key to disconnect.")],
) -> None:
    """Disconnect and remove a peer."""
    from saturnzap import node as node_mod

    node_mod.disconnect_peer(pubkey)
    output.ok(node_id=pubkey, message="Peer removed.")


# ── Phase 2: Channels ───────────────────────────────────────────

channels_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
app.add_typer(channels_app, name="channels", help="Manage Lightning channels.")


@channels_app.command("list")
def channels_list() -> None:
    """List all channels."""
    from saturnzap import node as node_mod

    output.ok(channels=node_mod.list_channels())


@channels_app.command("open")
def channels_open(
    peer: Annotated[
        str | None,
        typer.Option(help="Peer as <pubkey>@<host>:<port>"),
    ] = None,
    lsp: Annotated[
        str | None,
        typer.Option(help="LSP name (e.g. 'lqwd')"),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option(help="LQWD region code (e.g. CA, US, JP)"),
    ] = None,
    amount_sats: Annotated[
        int,
        typer.Option("--amount-sats", help="Channel capacity in sats"),
    ] = 100_000,
    announce: Annotated[
        bool,
        typer.Option(help="Announce channel to the network"),
    ] = False,
) -> None:
    """Open a channel to a peer or via an LSP."""
    from saturnzap import node as node_mod

    if peer and lsp:
        output.error(
            "INVALID_ARGS", "Specify --peer or --lsp, not both.",
        )

    if lsp:
        node_id, address = _resolve_lsp(lsp, region)
    elif peer:
        node_id, address = _parse_peer_address(peer)
    else:
        output.error(
            "INVALID_ARGS", "Specify --peer <pubkey>@<host>:<port> or --lsp <name>.",
        )
        return  # unreachable, satisfies type checker

    ucid = node_mod.open_channel(
        node_id, address, amount_sats, announce=announce,
    )
    output.ok(
        user_channel_id=ucid,
        counterparty=node_id,
        amount_sats=amount_sats,
        message="Channel open initiated.",
    )


@channels_app.command("close")
def channels_close(
    channel_id: Annotated[
        str, typer.Option("--channel-id", help="Channel ID to close"),
    ],
    counterparty: Annotated[
        str, typer.Option(help="Counterparty public key"),
    ],
    force: Annotated[
        bool, typer.Option(help="Force-close the channel"),
    ] = False,
) -> None:
    """Close a channel cooperatively or by force."""
    from saturnzap import node as node_mod

    if force:
        node_mod.force_close_channel(channel_id, counterparty)
        output.ok(channel_id=channel_id, message="Force-close initiated.")
    else:
        node_mod.close_channel(channel_id, counterparty)
        output.ok(channel_id=channel_id, message="Cooperative close initiated.")


# ── Phase 4: L402 ───────────────────────────────────────────────


# ── Phase 5: Liquidity ──────────────────────────────────────────

liquidity_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
app.add_typer(
    liquidity_app, name="liquidity",
    help="Liquidity intelligence and management.",
)


@liquidity_app.command("status")
def liquidity_status() -> None:
    """Show channel health scores and recommendations."""
    from saturnzap import liquidity

    info = liquidity.get_status()
    output.ok(**info)


@liquidity_app.command("request-inbound")
def liquidity_request_inbound(
    amount_sats: Annotated[
        int,
        typer.Option("--amount-sats", help="Requested inbound capacity in sats"),
    ],
    region: Annotated[
        str | None,
        typer.Option("--region", help="Target LQWD region code (e.g. CA, US, JP)"),
    ] = None,
) -> None:
    """Request inbound liquidity from an LQWD node."""
    from saturnzap import liquidity

    info = liquidity.request_inbound(amount_sats, region)
    output.ok(**info)


# ── Phase 4: L402 (fetch) ───────────────────────────────────────


@app.command()
def fetch(
    url: Annotated[
        str,
        typer.Argument(help="URL to fetch (L402 auto-pay if 402)."),
    ],
    method: Annotated[
        str,
        typer.Option("--method", "-X", help="HTTP method"),
    ] = "GET",
    header: Annotated[
        list[str] | None,
        typer.Option("--header", "-H", help="Extra headers (key: value). Repeatable."),
    ] = None,
    data: Annotated[
        str | None,
        typer.Option("--data", "-d", help="Request body"),
    ] = None,
    max_sats: Annotated[
        int | None,
        typer.Option("--max-sats", help="Spending cap per request in sats"),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="HTTP timeout in seconds"),
    ] = 30.0,
) -> None:
    """Fetch a URL. Auto-detects HTTP 402, pays the invoice, and retries."""
    from saturnzap import l402

    extra_headers: dict[str, str] = {}
    for h in (header or []):
        if ":" not in h:
            output.error("INVALID_HEADER", f"Header must be 'key: value', got: {h}")
        key, val = h.split(":", 1)
        extra_headers[key.strip()] = val.strip()

    result = l402.fetch(
        url,
        method=method,
        headers=extra_headers or None,
        body=data,
        max_sats=max_sats,
        timeout=timeout,
    )

    # Build response dict matching the JSON contract in README
    resp: dict = {
        "url": result.url,
        "http_status": result.http_status,
    }
    if result.payment_hash:
        resp["payment_hash"] = result.payment_hash
        resp["amount_sats"] = result.amount_sats
        resp["fee_sats"] = result.fee_sats
    resp["duration_ms"] = result.duration_ms

    # Try to parse body as JSON; fall back to raw string
    import json
    try:
        resp["body"] = json.loads(result.body)
    except (json.JSONDecodeError, ValueError):
        resp["body"] = result.body

    output.ok(**resp)


# ── MCP Server ──────────────────────────────────────────────────


@app.command()
def mcp() -> None:
    """Start the MCP (Model Context Protocol) server on stdio."""
    from saturnzap.mcp_server import serve

    serve()


# ── Helpers ──────────────────────────────────────────────────────


def _parse_peer_address(target: str) -> tuple[str, str]:
    """Parse '<pubkey>@<host>:<port>' into (pubkey, host:port)."""
    if "@" not in target:
        output.error(
            "INVALID_PEER_ADDRESS",
            "Expected format: <pubkey>@<host>:<port>",
        )
    node_id, address = target.split("@", 1)
    return node_id, address


def _resolve_lsp(name: str, region: str | None) -> tuple[str, str]:
    """Resolve an LSP name to (pubkey, address)."""
    from saturnzap import lqwd

    if name.lower() != "lqwd":
        output.error("UNKNOWN_LSP", f"Unknown LSP: {name}. Supported: lqwd")

    if region:
        nodes = lqwd.list_nodes(region)
        if not nodes:
            output.error(
                "UNKNOWN_REGION",
                f"No LQWD node in region '{region}'. "
                f"Available: {', '.join(n['region'] for n in lqwd.NODES)}",
            )
        node = nodes[0]
    else:
        node = lqwd.get_nearest()

    return node["pubkey"], node["address"]
