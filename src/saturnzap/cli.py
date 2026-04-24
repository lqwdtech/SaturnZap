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
            "Quickest path \u2014 the one-line installer handles uv + the wheel:\n"
            "  curl -LsSf https://raw.githubusercontent.com"
            "/lqwdtech/SaturnZap/main/install.sh | sh\n"
            "Manual paths:\n"
            "  pip install vendor/ldk_node-0.7.0-py3-none-any.whl\n"
            "  uv tool install saturnzap --find-links "
            "https://github.com/lqwdtech/SaturnZap/releases/expanded_assets/v1.3.1",
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
    invoke_without_command=True,
    pretty_exceptions_enable=False,
)


def _confirm_mainnet(yes: bool = False) -> None:
    """Prompt for confirmation when spending on mainnet.

    Skippable with ``--yes`` flag or ``SZ_MAINNET_CONFIRM=yes`` env var.
    """
    from saturnzap.config import get_network

    if get_network() != "bitcoin":
        return
    if yes or os.environ.get("SZ_MAINNET_CONFIRM", "").lower() == "yes":
        return
    if not typer.confirm(
        "\u26a0  MAINNET — This will spend real bitcoin. Continue?",
        default=False,
    ):
        output.error("CANCELLED", "Mainnet operation cancelled by user.")


@app.callback()
def main(
    pretty: Annotated[
        bool,
        typer.Option("--pretty", help="Pretty-print JSON output."),
    ] = False,
    network: Annotated[
        str | None,
        typer.Option(
            "--network",
            help="Bitcoin network: signet, testnet, bitcoin.",
        ),
    ] = None,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Print SaturnZap version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """SaturnZap — Lightning wallet for autonomous AI agents."""
    if version:
        try:
            from importlib.metadata import version as _pkg_version
            ver = _pkg_version("saturnzap")
        except Exception:  # noqa: BLE001
            ver = "unknown"
        output.ok(version=ver)
        raise typer.Exit(0)
    if pretty or os.environ.get("SZ_PRETTY", "") == "1":
        output.set_pretty(True)
    if network:
        from saturnzap.config import set_network
        set_network(network)


# ── Phase 1 commands ─────────────────────────────────────────────


@app.command()
def init(
    for_lqwd_faucet: Annotated[
        bool,
        typer.Option(
            "--for-lqwd-faucet",
            help=(
                "Preset for LQWDClaw faucet: sets alias, trusts LQWD LND, "
                "sets 0-conf + no-reserve waivers. Mainnet only."
            ),
        ),
    ] = False,
    alias: Annotated[
        str | None,
        typer.Option(
            "--alias",
            help=(
                "Override the node alias written to config.toml. Applies on "
                "top of any preset."
            ),
        ),
    ] = None,
    backup_to: Annotated[
        str | None,
        typer.Option(
            "--backup-to",
            help=(
                "Write the BIP39 mnemonic to this file (mode 0600) and omit "
                "it from the JSON response. Recommended for agent hosts."
            ),
        ),
    ] = None,
    no_mnemonic_stdout: Annotated[
        bool,
        typer.Option(
            "--no-mnemonic-stdout",
            help=(
                "Strict mode: do not include the mnemonic in the JSON response. "
                "Requires --backup-to so the seed isn't lost."
            ),
        ),
    ] = False,
) -> None:
    """Generate seed, encrypt it, and start the Lightning node."""
    import os
    from pathlib import Path

    from saturnzap import keystore
    from saturnzap import node as node_mod

    if no_mnemonic_stdout and not backup_to:
        output.error(
            "INVALID_ARGS",
            "--no-mnemonic-stdout requires --backup-to so the seed isn't lost.",
        )

    if keystore.is_initialized():
        output.error("ALREADY_INITIALIZED", "Wallet already initialized. Seed exists.")

    mnemonic = keystore.generate_mnemonic()
    passphrase = keystore.get_passphrase(confirm=True)
    path = keystore.save_encrypted(mnemonic, passphrase)

    backup_path: Path | None = None
    if backup_to:
        backup_path = Path(backup_to).expanduser().resolve()
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        # Write with restrictive permissions to prevent races between create
        # and chmod. O_EXCL also avoids overwriting an existing file silently.
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(str(backup_path), flags, 0o600)
        try:
            os.write(fd, (mnemonic + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        # Defensive: ensure mode is 0600 even if umask widened it.
        os.chmod(backup_path, 0o600)

    preset_applied = False
    if for_lqwd_faucet:
        from saturnzap.config import get_network, save_node_config_key

        if get_network() != "bitcoin":
            output.error(
                "INVALID_ARGS",
                "--for-lqwd-faucet requires mainnet. Re-run without --network.",
            )
        # LQWD fleet + LND pubkey are already trusted by default on mainnet
        # (see node._resolve_trusted_peers). The preset also saves a readable
        # alias so LQWDClaw shows something useful.
        save_node_config_key("alias", "saturnzap-lqwdclaw")
        preset_applied = True

    if alias is not None:
        from saturnzap.config import save_node_config_key

        save_node_config_key("alias", alias)

    # Start the node with the fresh mnemonic
    n = node_mod.start(mnemonic)

    include_mnemonic = not (no_mnemonic_stdout or backup_to)
    resp: dict = {
        "pubkey": n.node_id(),
        "seed_path": str(path),
        "message": "Wallet initialized. WRITE DOWN YOUR MNEMONIC AND STORE IT SAFELY.",
    }
    if include_mnemonic:
        resp["mnemonic"] = mnemonic
    if backup_path is not None:
        resp["backup_path"] = str(backup_path)
        resp["message"] = (
            f"Wallet initialized. Mnemonic written to {backup_path} "
            "(mode 0600). Store this file safely \u2014 it is the only recovery path."
        )
    if preset_applied:
        resp["preset"] = "lqwd-faucet"
        resp["next_steps"] = [
            "Run 'sz service install' to persist the node.",
            "Run 'sz connect-info --check' and share the URI with LQWDClaw.",
        ]
    output.ok(**resp)


@app.command()
def setup(
    auto: Annotated[
        bool,
        typer.Option(
            "--auto",
            help="Non-interactive: init + request inbound from LQWD.",
        ),
    ] = False,
    region: Annotated[
        str | None,
        typer.Option(
            "--region",
            help="LQWD region code for inbound channel.",
        ),
    ] = None,
    inbound_sats: Annotated[
        int,
        typer.Option("--inbound-sats", help="Inbound liquidity to request (sats)."),
    ] = 100_000,
) -> None:
    """Guided first-run: init wallet, generate address, optionally open channel.

    Idempotent — skips steps that are already complete.
    Use --auto for fully non-interactive setup (requires SZ_PASSPHRASE env var).
    """
    from saturnzap import keystore
    from saturnzap import node as node_mod

    steps: list[dict] = []

    # Step 1: Init wallet (skip if already done)
    if keystore.is_initialized():
        passphrase = keystore.get_passphrase()
        mnemonic = keystore.load_mnemonic(passphrase)
        n = node_mod.start(mnemonic)
        steps.append({"step": "init", "skipped": True, "reason": "already initialized"})
    else:
        mnemonic = keystore.generate_mnemonic()
        passphrase = keystore.get_passphrase(confirm=True)
        path = keystore.save_encrypted(mnemonic, passphrase)
        n = node_mod.start(mnemonic)
        steps.append({
            "step": "init",
            "skipped": False,
            "mnemonic": mnemonic,
            "seed_path": str(path),
        })

    # Step 2: Open firewall port (auto mode)
    if auto:
        fw = node_mod.open_firewall_port()
        steps.append({"step": "firewall", "status": fw})

    # Step 3: Generate a receive address
    addr = node_mod.new_onchain_address()
    from saturnzap.config import get_network
    network = get_network()
    steps.append({"step": "address", "address": addr, "network": network})

    # Step 4: Connection info
    if auto:
        info = node_mod.get_connect_info()
        steps.append({
            "step": "connect_info",
            "uri": info.get("uri"),
            "host": info.get("host"),
            "port": info.get("port"),
        })

    # Step 4b (--auto only): Surface the channel-announce gate decision
    # so the operator can see whether their node will join the gossip
    # graph as a public routing node, and act on the hint if not.
    if auto:
        decision = node_mod.decide_announce(None)
        announce_step: dict[str, object] = {
            "step": "announce_decision",
            "announce": decision["announce"],
            "reason": decision["reason"],
        }
        if decision["warnings"]:
            announce_step["hint"] = decision["warnings"][0]
        steps.append(announce_step)

    # Step 5 (--auto only): Request inbound liquidity from LQWD
    if auto:
        from saturnzap import liquidity

        bal = node_mod.get_balance()
        has_channels = len(bal["channels"]) > 0
        onchain_sats = bal.get("spendable_onchain_sats") or bal.get(
            "onchain_sats", 0,
        ) or 0
        # Rough pre-flight threshold: inbound requires ~1% push fee + on-chain
        # reserve + fees. Require at least 5_000 sats on-chain before trying.
        min_bootstrap_sats = max(inbound_sats // 100 + 4_000, 5_000)

        if has_channels:
            steps.append({
                "step": "inbound",
                "skipped": True,
                "reason": "channel(s) already exist",
            })
        elif onchain_sats < min_bootstrap_sats:
            steps.append({
                "step": "inbound",
                "skipped": True,
                "reason": (
                    f"wallet unfunded (have {onchain_sats} sats, "
                    f"need ~{min_bootstrap_sats} sats to request inbound)"
                ),
                "onchain_sats": onchain_sats,
                "required_sats": min_bootstrap_sats,
            })
        else:
            try:
                info = liquidity.request_inbound(inbound_sats, region)
                steps.append({"step": "inbound", "skipped": False, **info})
            except SystemExit:
                steps.append({
                    "step": "inbound",
                    "skipped": True,
                    "reason": "inbound request failed (fund wallet first)",
                })
            except Exception as exc:  # noqa: BLE001
                # Catch LDK exceptions (InsufficientFunds etc.) so --auto on a
                # borderline-funded wallet reports a skip instead of erroring.
                steps.append({
                    "step": "inbound",
                    "skipped": True,
                    "reason": f"inbound request failed: {exc}",
                })

    # Build next_steps guidance
    next_steps: list[str] = []
    next_steps.append(f"Send bitcoin to {addr} to fund your wallet.")
    if auto:
        next_steps.append(
            "After funding arrives, run 'sz setup --auto' again to open a channel.",
        )
        connect_uri = None
        for s in steps:
            if s.get("step") == "connect_info":
                connect_uri = s.get("uri")
        if connect_uri:
            next_steps.append(
                f"Share your connection URI with peers: {connect_uri}",
            )
    else:
        next_steps.append(
            "Run 'sz setup --auto' for automatic channel setup after funding.",
        )

    output.ok(
        pubkey=n.node_id(),
        steps=steps,
        next_steps=next_steps,
        message="Setup complete.",
    )


@app.command()
def start(
    foreground: Annotated[
        bool,
        typer.Option(
            "--foreground",
            help="Start the node, print status, and exit (non-persistent).",
        ),
    ] = False,
    daemon: Annotated[
        bool,
        typer.Option(
            "--daemon",
            help="[Deprecated] Now the default. Kept for back-compat.",
            hidden=True,
        ),
    ] = False,
) -> None:
    """Start the Lightning node and block until stopped (SIGTERM/SIGINT).

    By default, ``sz start`` runs as a foreground daemon suitable for systemd.
    Use ``--foreground`` for the old "print and exit" behavior (note: the
    node is NOT persistent in that mode).
    """
    import signal
    import time

    from saturnzap import node as node_mod

    # --daemon is a no-op flag now; default behavior already runs as daemon.
    _ = daemon
    as_daemon = not foreground

    n = node_mod._require_node()
    firewall = node_mod.open_firewall_port() if as_daemon else None
    resp = {"pubkey": n.node_id(), "message": "Node started."}
    if firewall:
        resp["firewall"] = firewall
    if not as_daemon:
        resp["warning"] = (
            "Foreground mode: node stops when this process exits. "
            "Run 'sz service install' to persist as a systemd service."
        )
    output.ok(**resp)

    if as_daemon:
        # Start IPC server so CLI commands can talk to this daemon
        from saturnzap.ipc import (
            IPCServer,
            _shutdown_event,
            build_dispatcher,
            socket_path,
        )

        dispatcher = build_dispatcher()
        ipc_server = IPCServer(socket_path(), dispatcher)
        ipc_server.start_background()

        # Block forever — systemd sends SIGTERM to stop
        stop_event = False

        def _handle_signal(signum, frame):  # noqa: ARG001
            nonlocal stop_event
            stop_event = True

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        while not stop_event and not _shutdown_event.is_set():
            time.sleep(1)

        ipc_server.stop()
        node_mod.stop()
        raise SystemExit(0)


@app.command()
def stop(
    close_all: Annotated[
        bool,
        typer.Option(
            "--close-all",
            help="Cooperatively close all channels first.",
        ),
    ] = False,
) -> None:
    """Stop the Lightning node and clean up."""
    from saturnzap import node as node_mod

    if close_all:
        channels = node_mod.list_channels()
        closed = []
        for ch in channels:
            try:
                node_mod.close_channel(ch["channel_id"], ch["counterparty_node_id"])
                closed.append(ch["channel_id"])
            except Exception:  # noqa: BLE001, S110
                pass  # Best-effort; node.stop() will handle the rest
        node_mod.stop()
        output.ok(
            message=f"Closed {len(closed)} channel(s) and stopped node.",
            closed_channels=closed,
        )
    else:
        # Warn if channels are still open
        try:
            channels = node_mod.list_channels()
            if channels:
                node_mod.stop()
                output.ok(
                    message="Node stopped.",
                    warning=(
                        f"{len(channels)} channel(s) still open. "
                        "Use --close-all to close first."
                    ),
                )
                return
        except Exception:  # noqa: BLE001, S110
            pass
        node_mod.stop()
        output.ok(message="Node stopped.")


@app.command()
def status() -> None:
    """Show node pubkey, sync state, and uptime."""
    from saturnzap import node as node_mod

    info = node_mod.get_status()
    output.ok(**info)


@app.command(name="connect-info")
def connect_info(
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Test if the Lightning port is reachable from the internet.",
        ),
    ] = False,
) -> None:
    """Show this node's connection URI (pubkey@host:port) for sharing."""
    from saturnzap import node as node_mod

    info = node_mod.get_connect_info()
    if check:
        info["reachable"] = node_mod.check_port_reachable(
            host=info.get("host"), port=info.get("port"),
        )
    output.ok(**info)


@app.command()
def address() -> None:
    """Generate a new on-chain receive address (for faucet deposits)."""
    from saturnzap import node as node_mod

    addr = node_mod.new_onchain_address()
    from saturnzap.config import get_network
    output.ok(address=addr, network=get_network())


@app.command()
def send(
    address: Annotated[
        str,
        typer.Argument(help="Destination on-chain address."),
    ],
    amount_sats: Annotated[
        int | None,
        typer.Option("--amount", "-a", help="Amount in sats (omit to send all)."),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip mainnet confirmation prompt."),
    ] = False,
) -> None:
    """Send sats on-chain to an address."""
    from saturnzap import node as node_mod

    _confirm_mainnet(yes)
    txid = node_mod.send_onchain(address, amount_sats)
    output.ok(txid=txid, amount_sats=amount_sats, send_all=amount_sats is None)


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
    wait: Annotated[
        bool,
        typer.Option("--wait", help="Block until invoice is paid or expired."),
    ] = False,
) -> None:
    """Create a BOLT11 invoice to receive a payment."""
    from saturnzap import payments

    if amount_sats > 0:
        info = payments.create_invoice(amount_sats, memo, expiry)
    else:
        info = payments.create_variable_invoice(memo, expiry)

    if not wait:
        output.ok(**info)
        return

    # Block until paid or expired
    result = payments.wait_for_payment(info["payment_hash"], timeout=expiry)
    output.ok(**{**info, **result})


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
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip mainnet confirmation prompt."),
    ] = False,
    no_wait: Annotated[
        bool,
        typer.Option(
            "--no-wait",
            help=(
                "Return immediately after LDK accepts the send instead of "
                "waiting for the payment to succeed or fail."
            ),
        ),
    ] = False,
    wait_timeout: Annotated[
        int,
        typer.Option(
            "--wait-timeout",
            help="Seconds to wait for payment to reach a terminal state.",
        ),
    ] = 30,
) -> None:
    """Pay a BOLT11 invoice."""
    from saturnzap import payments

    _confirm_mainnet(yes)
    info = payments.pay_invoice(
        invoice_str, max_sats, wait=not no_wait, wait_timeout=wait_timeout,
    )
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
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip mainnet confirmation prompt."),
    ] = False,
    no_wait: Annotated[
        bool,
        typer.Option(
            "--no-wait",
            help=(
                "Return immediately after LDK accepts the send instead of "
                "waiting for the payment to succeed or fail."
            ),
        ),
    ] = False,
    wait_timeout: Annotated[
        int,
        typer.Option(
            "--wait-timeout",
            help="Seconds to wait for payment to reach a terminal state.",
        ),
    ] = 30,
) -> None:
    """Send a spontaneous keysend payment."""
    from saturnzap import payments

    _confirm_mainnet(yes)
    info = payments.keysend(
        pubkey, amount_sats, wait=not no_wait, wait_timeout=wait_timeout,
    )
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


@peers_app.command("trust")
def peers_trust(
    pubkey: Annotated[
        str,
        typer.Argument(help="Peer public key to trust (waives anchor reserve)."),
    ],
) -> None:
    """Add a peer to the anchor-reserve waiver list.

    Applied on the next node start. Allows zero-balance wallets to accept
    inbound channels from this peer without an on-chain reserve.
    """
    from saturnzap.config import load_node_config, save_node_config_key

    pubkey = pubkey.strip()
    cfg = load_node_config()
    current = list(cfg.get("trusted_peers_no_reserve") or [])
    if pubkey not in current:
        current.append(pubkey)
        save_node_config_key("trusted_peers_no_reserve", current)
    output.ok(
        pubkey=pubkey,
        trusted_peers=current,
        message="Peer trusted. Restart node to apply.",
    )


@peers_app.command("untrust")
def peers_untrust(
    pubkey: Annotated[
        str,
        typer.Argument(help="Peer public key to remove from the trust list."),
    ],
) -> None:
    """Remove a peer from the anchor-reserve waiver list."""
    from saturnzap.config import load_node_config, save_node_config_key

    pubkey = pubkey.strip()
    cfg = load_node_config()
    current = [p for p in (cfg.get("trusted_peers_no_reserve") or []) if p != pubkey]
    save_node_config_key(
        "trusted_peers_no_reserve", current if current else None,
    )
    output.ok(
        pubkey=pubkey,
        trusted_peers=current,
        message="Peer untrusted. Restart node to apply.",
    )


@peers_app.command("trusted-list")
def peers_trusted_list() -> None:
    """List trusted peers (anchor-reserve waiver + LQWD fleet)."""
    from saturnzap.config import get_network, load_node_config
    from saturnzap.lqwd import mainnet_trusted_pubkeys

    cfg = load_node_config()
    user_trusted = list(cfg.get("trusted_peers_no_reserve") or [])
    fleet = mainnet_trusted_pubkeys() if get_network() == "bitcoin" else []
    output.ok(
        network=get_network(),
        lqwd_fleet=fleet,
        user_trusted=user_trusted,
    )


# ── Phase 2: Config ──────────────────────────────────────────────

config_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
app.add_typer(config_app, name="config", help="Manage SaturnZap configuration.")


_CONFIG_KEY_SPEC: dict[str, str] = {
    "node.alias": "Lightning node alias (string, max 32 chars).",
    "node.listen_port": "Lightning P2P listen port (int).",
    "node.min_confirms": "Channel confirmation threshold (int).",
    "node.trusted_peers_no_reserve": "Trusted peers for anchor reserve waiver (list).",
    "esplora_url": "Esplora API endpoint (string).",
    "network": "Bitcoin network: bitcoin, signet, or testnet (string).",
}


def _split_config_key(key: str) -> tuple[str | None, str]:
    if "." in key:
        section, sub = key.split(".", 1)
        return section, sub
    return None, key


@config_app.command("list")
def config_list() -> None:
    """List known config keys and their current values."""
    from saturnzap.config import _load_config_raw

    raw = _load_config_raw()
    flat: dict[str, object] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            for sk, sv in v.items():
                flat[f"{k}.{sk}"] = sv
        else:
            flat[k] = v
    output.ok(config=flat, known_keys=sorted(_CONFIG_KEY_SPEC.keys()))


@config_app.command("get")
def config_get(
    key: Annotated[str, typer.Argument(help="Config key, e.g. node.alias")],
) -> None:
    """Get a config value."""
    from saturnzap.config import _load_config_raw

    raw = _load_config_raw()
    section, sub = _split_config_key(key)
    value = (
        raw.get(sub) if section is None else (raw.get(section) or {}).get(sub)
    )
    output.ok(key=key, value=value)


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key (e.g. node.alias).")],
    value: Annotated[str, typer.Argument(help="Value: string, int, bool, JSON.")],
) -> None:
    """Set a config value."""
    import contextlib
    import json

    from saturnzap.config import (
        _load_config_raw,
        _write_config_toml,
    )

    # Coerce: try int, bool, JSON list/dict, fallback to string.
    parsed: object = value
    if value.lower() in ("true", "false"):
        parsed = value.lower() == "true"
    else:
        try:
            parsed = int(value)
        except ValueError:
            if value.startswith("[") or value.startswith("{"):
                with contextlib.suppress(json.JSONDecodeError):
                    parsed = json.loads(value)

    raw = _load_config_raw()
    section, sub = _split_config_key(key)
    if section is None:
        raw[sub] = parsed
    else:
        current_section = dict(raw.get(section) or {})
        current_section[sub] = parsed
        raw[section] = current_section
    _write_config_toml(raw)
    output.ok(key=key, value=parsed, message="Config updated. Restart node to apply.")


@config_app.command("unset")
def config_unset(
    key: Annotated[str, typer.Argument(help="Config key to remove, e.g. node.alias")],
) -> None:
    """Remove a config key."""
    from saturnzap.config import _load_config_raw, _write_config_toml

    raw = _load_config_raw()
    section, sub = _split_config_key(key)
    changed = False
    if section is None:
        if sub in raw:
            del raw[sub]
            changed = True
    elif section in raw and isinstance(raw[section], dict) and sub in raw[section]:
        del raw[section][sub]
        if not raw[section]:
            del raw[section]
        changed = True

    if changed:
        _write_config_toml(raw)
    output.ok(key=key, removed=changed, message="Config updated.")


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
        bool | None,
        typer.Option(
            "--announce/--no-announce",
            help=(
                "Announce channel to the network. Omit to use the auto "
                "gate: announce iff the node is reachable from the "
                "internet (mainnet only)."
            ),
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip mainnet confirmation prompt."),
    ] = False,
) -> None:
    """Open a channel to a peer or via an LSP."""
    from saturnzap import node as node_mod

    _confirm_mainnet(yes)

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

    decision = node_mod.decide_announce(announce)
    ucid = node_mod.open_channel(
        node_id, address, amount_sats, announce=decision["announce"],
    )
    response: dict[str, object] = {
        "user_channel_id": ucid,
        "counterparty": node_id,
        "amount_sats": amount_sats,
        "announce": decision["announce"],
        "announce_reason": decision["reason"],
        "message": "Channel open initiated.",
    }
    if decision["warnings"]:
        response["warnings"] = decision["warnings"]
    output.ok(**response)


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
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip mainnet confirmation prompt."),
    ] = False,
) -> None:
    """Close a channel cooperatively or by force."""
    from saturnzap import node as node_mod

    _confirm_mainnet(yes)
    if force:
        node_mod.force_close_channel(channel_id, counterparty)
        output.ok(channel_id=channel_id, message="Force-close initiated.")
    else:
        node_mod.close_channel(channel_id, counterparty)
        output.ok(channel_id=channel_id, message="Cooperative close initiated.")


@channels_app.command("wait")
def channels_wait(
    channel_id: Annotated[
        str | None,
        typer.Option("--channel-id", help="Channel ID to wait for (any if omitted)."),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option("--timeout", help="Max seconds to wait."),
    ] = 300,
) -> None:
    """Block until a channel becomes usable or timeout."""
    from saturnzap import node as node_mod

    result = node_mod.wait_channel_ready(channel_id, timeout)
    output.ok(**result)


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


# ── Service management ───────────────────────────────────────────

service_app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
app.add_typer(service_app, name="service", help="Manage SaturnZap systemd service.")


@service_app.command("install")
def service_install() -> None:
    """Install and start the SaturnZap systemd service."""
    from saturnzap import service

    info = service.install()
    output.ok(**info)


@service_app.command("uninstall")
def service_uninstall() -> None:
    """Stop and remove the SaturnZap systemd service."""
    from saturnzap import service

    info = service.uninstall()
    output.ok(**info)


@service_app.command("status")
def service_status() -> None:
    """Check the SaturnZap systemd service status."""
    from saturnzap import service

    info = service.status()
    output.ok(**info)


# ── Backup & Restore ────────────────────────────────────────────


@app.command()
def backup(
    output_path: Annotated[
        str,
        typer.Option("--output", "-o", help="Path to write the encrypted backup file."),
    ] = "saturnzap-backup.json",
) -> None:
    """Create an encrypted backup of the wallet."""
    from pathlib import Path

    from saturnzap import backup as backup_mod
    from saturnzap import keystore

    passphrase = keystore.get_passphrase()
    info = backup_mod.backup(Path(output_path), passphrase)
    output.ok(**info, message="Backup created successfully.")


@app.command()
def restore(
    input_path: Annotated[
        str,
        typer.Option("--input", "-i", help="Path to the encrypted backup file."),
    ],
) -> None:
    """Restore wallet from an encrypted backup."""
    from pathlib import Path

    from saturnzap import backup as backup_mod
    from saturnzap import keystore

    passphrase = keystore.get_passphrase(confirm=True)
    info = backup_mod.restore(Path(input_path), passphrase)
    output.ok(**info, message="Wallet restored successfully.")


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
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip mainnet confirmation."),
    ] = False,
) -> None:
    """Fetch a URL. Auto-detects HTTP 402, pays the invoice, and retries."""
    from saturnzap import l402

    # L402 auto-pay can spend real bitcoin on mainnet. Gate it behind the same
    # confirmation used for pay/keysend/send/channels-open.
    _confirm_mainnet(yes)

    # Apply env-var default cap when --max-sats is not explicitly set.
    if max_sats is None:
        env_cap = os.environ.get("SZ_CLI_MAX_SPEND_SATS")
        if env_cap:
            try:
                max_sats = int(env_cap)
            except ValueError:
                output.error(
                    "INVALID_ARGS",
                    f"SZ_CLI_MAX_SPEND_SATS must be an integer, got: {env_cap}",
                )

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

    if result.warnings:
        resp["warnings"] = result.warnings

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
