"""LDK Node lifecycle — build, start, stop, status, peers, channels."""

from __future__ import annotations

from pathlib import Path

from ldk_node import Builder, Network, Node, default_config

from saturnzap.config import (
    DEFAULT_LISTEN_PORTS,
    data_dir,
    get_network,
    load_config,
    resolve_esplora,
)

_node: Node | None = None

# ── IPC routing ──────────────────────────────────────────────────
# When a daemon is running, CLI commands become thin clients.  Each
# public function checks _use_ipc() first; if True, the call is
# forwarded over the Unix Domain Socket and the local LDK node is
# never touched.

_ipc_mode: bool = False


def _use_ipc() -> bool:
    """Return True if calls should route through the daemon socket.

    Auto-detects: if no local node is running but a daemon socket
    exists and is responsive, switch to IPC mode.
    """
    global _ipc_mode  # noqa: PLW0603
    if _ipc_mode:
        return True
    if _node is not None:
        return False
    # Lazy import to keep module import fast
    from saturnzap.ipc import daemon_is_running

    if daemon_is_running():
        _ipc_mode = True
        return True
    return False


def _ipc(method: str, **params: object) -> object:
    """Send an IPC call to the daemon.  Convenience wrapper."""
    from saturnzap.ipc import ipc_call

    return ipc_call(method, params if params else None)

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
    network_name = get_network()
    network = _network_from_str(network_name)
    esplora_url = resolve_esplora(network_name, cfg.get("esplora_url"))

    config = default_config()

    # ── Node alias ────────────────────────────────────────────────
    # LDK Node rejects inbound announced channels when alias is None.
    # Priority: SZ_ALIAS env > [node].alias in config.toml > deterministic default.
    config.node_alias = _resolve_node_alias(mnemonic)

    # ── Anchor channel reserve waiver ─────────────────────────────
    # LDK Node's default 25_000 sat per-channel reserve blocks zero-balance
    # wallets from accepting their first inbound channel. Trust LQWD fleet
    # pubkeys (and any user-configured peers) so faucet/LSP channels open
    # without an on-chain reserve requirement.
    if config.anchor_channels_config is not None and network_name == "bitcoin":
        config.anchor_channels_config.trusted_peers_no_reserve = (
            _resolve_trusted_peers()
        )

    # ── Zero-conf channels from trusted peers ─────────────────────
    # Accept channels from LQWD fleet nodes at 0 confirmations instead of the
    # LDK default of 6. Cuts time-to-usable from ~60 min to ~seconds for
    # faucet/LSP channels. Mainnet only.
    if network_name == "bitcoin":
        config.trusted_peers_0conf = _resolve_trusted_peers()

    builder = Builder.from_config(config)
    builder.set_network(network)
    builder.set_storage_dir_path(_node_storage())
    builder.set_chain_source_esplora(esplora_url, None)
    builder.set_entropy_bip39_mnemonic(mnemonic, None)
    listen_port = _resolve_listen_port(network_name)
    builder.set_listening_addresses([f"0.0.0.0:{listen_port}"])
    builder.set_gossip_source_p2p()

    return builder.build()


def _resolve_node_alias(mnemonic: str) -> str:
    """Resolve the LDK node alias.

    Priority: ``SZ_ALIAS`` env var → ``[node].alias`` in config.toml →
    deterministic ``saturnzap-<6-hex>`` derived from the mnemonic.
    """
    import hashlib
    import os

    env_alias = os.environ.get("SZ_ALIAS", "").strip()
    if env_alias:
        return env_alias[:32]

    from saturnzap.config import load_node_config

    node_cfg = load_node_config()
    cfg_alias = str(node_cfg.get("alias", "")).strip()
    if cfg_alias:
        return cfg_alias[:32]

    # Deterministic fallback: stable across restarts, unique per wallet.
    digest = hashlib.sha256(mnemonic.encode("utf-8")).hexdigest()
    return f"saturnzap-{digest[:6]}"


def _resolve_trusted_peers() -> list[str]:
    """Resolve the mainnet trusted-peer list for anchor reserve waivers.

    Combines LQWD fleet pubkeys, config-file entries, and the
    ``SZ_TRUSTED_PEERS_NO_RESERVE`` env var (comma-separated).
    """
    import os

    from saturnzap.config import load_node_config
    from saturnzap.lqwd import mainnet_trusted_pubkeys

    pubkeys: list[str] = list(mainnet_trusted_pubkeys())

    node_cfg = load_node_config()
    cfg_extra = node_cfg.get("trusted_peers_no_reserve", []) or []
    if isinstance(cfg_extra, list):
        pubkeys.extend(str(p).strip() for p in cfg_extra if p)

    env_extra = os.environ.get("SZ_TRUSTED_PEERS_NO_RESERVE", "").strip()
    if env_extra:
        pubkeys.extend(p.strip() for p in env_extra.split(",") if p.strip())

    # De-dup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for pk in pubkeys:
        if pk and pk not in seen:
            seen.add(pk)
            out.append(pk)
    return out


def _resolve_listen_port(network_name: str) -> int:
    """Resolve the Lightning listen port.

    Priority: ``[node].listen_port`` in config.toml → ``DEFAULT_LISTEN_PORTS``.
    """
    from saturnzap.config import load_node_config

    node_cfg = load_node_config()
    port = node_cfg.get("listen_port")
    if port:
        try:
            return int(port)
        except (TypeError, ValueError):
            pass
    return DEFAULT_LISTEN_PORTS.get(network_name, 9735)


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
    global _node, _ipc_mode  # noqa: PLW0603
    # In IPC mode, tell the daemon to shut down.
    if _ipc_mode:
        _ipc("shutdown")
        _ipc_mode = False
        return
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
    if _use_ipc():
        return _ipc("get_status")  # type: ignore[return-value]
    import time

    node = _require_node()
    node.sync_wallets()
    st = node.status()

    peers = node.list_peers()
    channels = node.list_channels()
    usable = sum(1 for c in channels if c.is_usable)

    # Compute sync lag from latest wallet sync timestamp
    now_ts = int(time.time())
    wallet_ts = st.latest_onchain_wallet_sync_timestamp
    sync_lag_seconds = (now_ts - wallet_ts) if wallet_ts else None

    return {
        "pubkey": node.node_id(),
        "is_running": st.is_running,
        "network": get_network(),
        "block_height": st.current_best_block.height,
        "block_hash": st.current_best_block.block_hash,
        "latest_wallet_sync": st.latest_onchain_wallet_sync_timestamp,
        "latest_lightning_sync": st.latest_lightning_wallet_sync_timestamp,
        "peer_count": len(peers),
        "channel_count": len(channels),
        "usable_channel_count": usable,
        "sync_lag_seconds": sync_lag_seconds,
    }


def get_connect_info() -> dict:
    """Return the node's connection URI (pubkey@host:port) for sharing."""
    if _use_ipc():
        return _ipc("get_connect_info")  # type: ignore[return-value]
    node = _require_node()
    pubkey = node.node_id()
    network_name = get_network()
    port = _resolve_listen_port(network_name)

    # Detect external IP via a lightweight HTTP service
    host = _detect_external_ip()

    uri = f"{pubkey}@{host}:{port}" if host else None
    return {
        "pubkey": pubkey,
        "host": host,
        "port": port,
        "uri": uri,
        "network": network_name,
    }


def _detect_external_ip() -> str | None:
    """Best-effort external IP detection. Returns None on failure."""
    import httpx

    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ]
    for url in services:
        try:
            resp = httpx.get(url, timeout=3.0)
            if resp.status_code == 200:
                return resp.text.strip()
        except (httpx.HTTPError, OSError):
            continue
    return None


def open_firewall_port(port: int | None = None) -> str:
    """Open the Lightning P2P port in UFW if it's active.

    Returns a status string:
      "opened"           — rule added successfully
      "already_open"     — rule already exists
      "ufw_inactive"     — UFW is installed but not enabled
      "ufw_not_found"    — UFW is not installed
      "not_linux"        — not running on Linux
      "permission_denied" — need root/sudo to modify UFW
      "error"            — unexpected failure
    """
    import platform
    import shutil
    import subprocess  # noqa: S404

    if platform.system() != "Linux":
        return "not_linux"

    ufw = shutil.which("ufw")
    if not ufw:
        return "ufw_not_found"

    if port is None:
        port = _resolve_listen_port(get_network())

    # Check if UFW is active
    try:
        result = subprocess.run(  # noqa: S603
            [ufw, "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except PermissionError:
        return "permission_denied"
    except (OSError, subprocess.TimeoutExpired):
        return "error"

    if "inactive" in result.stdout.lower():
        return "ufw_inactive"

    # Check if rule already exists
    if f"{port}/tcp" in result.stdout:
        return "already_open"

    # Add the rule
    try:
        add = subprocess.run(  # noqa: S603
            [ufw, "allow", f"{port}/tcp"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except PermissionError:
        return "permission_denied"
    except (OSError, subprocess.TimeoutExpired):
        return "error"

    if add.returncode == 0:
        return "opened"
    return "error"


def check_port_reachable(
    host: str | None = None, port: int | None = None,
) -> bool | None:
    """Best-effort check if this node's Lightning port is reachable from the internet.

    Uses an external port-check API. Returns True/False, or None if the check
    itself failed (service down, no internet, etc.).
    """
    if host is None:
        host = _detect_external_ip()
    if host is None:
        return None
    if port is None:
        port = _resolve_listen_port(get_network())

    # Check via a purpose-built port-check API.
    # check-host.net returns JSON from multiple geographic probe nodes; any
    # "OPEN" response is enough to confirm external reachability.
    result = _probe_check_host_net(host, port)
    if result is not None:
        return result

    return None


def _probe_check_host_net(host: str, port: int) -> bool | None:
    """Check external reachability via check-host.net multi-node probe.

    Returns True/False if the service responded, None on service failure.
    """
    import time

    import httpx

    try:
        submit = httpx.get(
            "https://check-host.net/check-tcp",
            params={"host": f"{host}:{port}", "max_nodes": 3},
            headers={"Accept": "application/json"},
            timeout=5.0,
        )
        if submit.status_code != 200:
            return None
        request_id = submit.json().get("request_id")
        if not request_id:
            return None
    except (httpx.HTTPError, OSError, ValueError):
        return None

    # Poll for results — nodes may take a few seconds to report.
    results_url = f"https://check-host.net/check-result/{request_id}"
    for _ in range(5):
        time.sleep(1.0)
        try:
            resp = httpx.get(
                results_url,
                headers={"Accept": "application/json"},
                timeout=5.0,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
        except (httpx.HTTPError, OSError, ValueError):
            continue

        # Shape: {"<node-id>": [[{"time": ..., "address": "<ip>:<port>"}]], ...}
        # A node that hasn't completed yet has value `null`.
        completed = [v for v in data.values() if v is not None]
        if not completed:
            continue

        for node_result in completed:
            if not node_result or not node_result[0]:
                continue
            # Per-node result list: each entry is either a success dict with
            # "address" or an error dict with "error" key.
            for attempt in node_result[0]:
                if isinstance(attempt, dict) and "address" in attempt:
                    return True
        # All completed probes reported errors (connection refused, timeout).
        if len(completed) >= len(data) / 2:
            return False

    return None


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
    if _use_ipc():
        return _ipc("new_onchain_address")  # type: ignore[return-value]
    return _require_node().onchain_payment().new_address()


def send_onchain(address: str, amount_sats: int | None = None) -> str:
    """Send sats on-chain. If *amount_sats* is None, send all funds."""
    from saturnzap import output

    if amount_sats is not None and amount_sats <= 0:
        output.error("INVALID_ARGS", "amount_sats must be positive (omit to sweep).")
    if _use_ipc():
        return _ipc("send_onchain", address=address, amount_sats=amount_sats)  # type: ignore[return-value]

    node = _require_node()
    node.sync_wallets()

    # Pre-flight balance check
    bal = node.list_balances()
    available = bal.spendable_onchain_balance_sats
    if amount_sats is not None and amount_sats > available:
        output.error(
            "INSUFFICIENT_FUNDS",
            f"Send requires {amount_sats} sats but spendable on-chain balance "
            f"is {available} sats.",
        )
    if amount_sats is None and available == 0:
        output.error(
            "INSUFFICIENT_FUNDS",
            "No spendable on-chain balance to send.",
        )

    op = node.onchain_payment()
    if amount_sats is None:
        txid = op.send_all_to_address(address, retain_reserve=False, fee_rate=None)
    else:
        txid = op.send_to_address(address, amount_sats, fee_rate=None)
    return str(txid)


def get_balance() -> dict:
    """Return on-chain and lightning balances."""
    if _use_ipc():
        return _ipc("get_balance")  # type: ignore[return-value]
    node = _require_node()
    node.sync_wallets()
    bal = node.list_balances()
    channels = [_channel_to_dict(c) for c in node.list_channels()]
    result = {
        "onchain_sats": bal.total_onchain_balance_sats,
        "spendable_onchain_sats": bal.spendable_onchain_balance_sats,
        "lightning_sats": bal.total_lightning_balance_sats,
        "anchor_reserve_sats": bal.total_anchor_channels_reserve_sats,
        "channels": channels,
    }

    # Balance-related warnings (no channels, critical health, etc.)
    from saturnzap import liquidity

    warnings = liquidity.balance_warnings(result)
    if warnings:
        result["warnings"] = warnings

    return result


# ── Peers ────────────────────────────────────────────────────────


def connect_peer(node_id: str, address: str, persist: bool = True) -> None:
    """Connect to a peer by pubkey and address (host:port)."""
    if _use_ipc():
        _ipc("connect_peer", node_id=node_id, address=address, persist=persist)
        return
    _require_node().connect(node_id, address, persist)


def disconnect_peer(node_id: str) -> None:
    """Disconnect from a peer."""
    if _use_ipc():
        _ipc("disconnect_peer", node_id=node_id)
        return
    _require_node().disconnect(node_id)


def list_peers() -> list[dict]:
    """Return list of peers as dicts."""
    if _use_ipc():
        return _ipc("list_peers")  # type: ignore[return-value]
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
    # Derive a human-readable status reason
    if c.is_usable:
        status_reason = "ready"
    elif not c.is_channel_ready:
        status_reason = "awaiting_confirmation"
    else:
        status_reason = "peer_offline"

    return {
        "channel_id": str(c.channel_id),
        "user_channel_id": str(c.user_channel_id),
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
        "status_reason": status_reason,
    }


def _resolve_user_channel_id(node, channel_id: str) -> str | None:
    """Resolve a caller-supplied channel identifier to LDK's user_channel_id.

    Accepts either the funding-tx ``channel_id`` (the hex hash shown in
    ``sz channels list``) or LDK's numeric ``user_channel_id``. Returns the
    matching user_channel_id, or ``None`` if no channel matches.
    """
    target = str(channel_id)
    for c in node.list_channels():
        if str(c.channel_id) == target or str(c.user_channel_id) == target:
            return str(c.user_channel_id)
    return None


def list_channels() -> list[dict]:
    """Return all channels as dicts."""
    if _use_ipc():
        return _ipc("list_channels")  # type: ignore[return-value]
    return [_channel_to_dict(c) for c in _require_node().list_channels()]


def wait_channel_ready(
    channel_id: str | None = None,
    timeout: int = 300,
    poll_interval: int = 5,
) -> dict:
    """Block until a channel becomes usable or timeout.

    Args:
        channel_id: Specific channel to wait for. If None, waits for any usable channel.
        timeout: Maximum seconds to wait.
        poll_interval: Seconds between checks.

    Returns:
        Dict with the ready channel info, or timeout status.
    """
    if _use_ipc():
        return _ipc(  # type: ignore[return-value]
            "wait_channel_ready",
            channel_id=channel_id, timeout=timeout, poll_interval=poll_interval,
        )
    import time

    node = _require_node()
    deadline = time.monotonic() + timeout

    def _matches(c) -> bool:
        if not channel_id:
            return True
        return str(c.channel_id) == channel_id or str(c.user_channel_id) == channel_id

    while time.monotonic() < deadline:
        node.sync_wallets()
        channels = node.list_channels()
        for c in channels:
            if not _matches(c):
                continue
            if c.is_usable:
                return {
                    "status": "ready",
                    "channel": _channel_to_dict(c),
                    "waited_seconds": int(timeout - (deadline - time.monotonic())),
                }
        time.sleep(poll_interval)

    # Timeout — return current state of the target channel(s)
    channels = node.list_channels()
    target = None
    for c in channels:
        if not _matches(c):
            continue
        target = _channel_to_dict(c)
        break

    return {
        "status": "timeout",
        "channel": target,
        "waited_seconds": timeout,
        "message": f"Channel not ready after {timeout}s.",
    }


def _parse_channel_rejection() -> str | None:
    """Read the LDK log for the most recent channel close reason.

    Returns the peer's rejection message, or None if not found or log unreadable.
    Never raises — failure to parse should not mask the original error context.
    """
    try:
        log_path = Path(_node_storage()) / "ldk_node.log"
        if not log_path.exists():
            return None
        # Read last 8KB — rejections appear within seconds of open_channel
        size = log_path.stat().st_size
        with log_path.open("rb") as f:
            f.seek(max(0, size - 8192))
            tail = f.read().decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return None

    # LDK logs close reasons in two forms:
    # ERROR: "Closed channel <id> due to close-required error: <reason>"
    # INFO:  "Channel <id> closed due to: <reason>"
    try:
        for line in reversed(tail.splitlines()):
            if "closed due to" in line.lower() or "close-required" in line.lower():
                for marker in [
                    "close-required error: ",
                    "closed due to: ",
                ]:
                    idx = line.lower().find(marker)
                    if idx != -1:
                        return line[idx + len(marker):].strip()
    except Exception:  # noqa: BLE001
        return None
    return None


def open_channel(
    node_id: str,
    address: str,
    amount_sats: int,
    *,
    push_msat: int | None = None,
    announce: bool = False,
) -> str:
    """Open a channel to a peer. Returns the user_channel_id.

    Waits briefly after sending the open request to detect immediate
    rejections (e.g. channel too small).  Raises ``CommandError`` with
    code ``CHANNEL_REJECTED`` if the peer rejects the channel.
    """
    from saturnzap import output

    if amount_sats <= 0:
        output.error("INVALID_ARGS", "amount_sats must be positive.")
    if push_msat is not None and push_msat < 0:
        output.error("INVALID_ARGS", "push_msat must be non-negative.")
    if _use_ipc():
        return _ipc(  # type: ignore[return-value]
            "open_channel",
            node_id=node_id, address=address, amount_sats=amount_sats,
            push_msat=push_msat, announce=announce,
        )
    node = _require_node()
    if announce:
        ucid = node.open_announced_channel(
            node_id, address, amount_sats, push_msat, None,
        )
    else:
        ucid = node.open_channel(
            node_id, address, amount_sats, push_msat, None,
        )
    ucid_str = str(ucid)

    # Poll for up to 3 seconds to detect an immediate rejection.
    # The channel either appears in list_channels() (accepted) or never shows
    # up (rejected). We poll every 250ms so fast rejections are caught quickly
    # and slow accepts still succeed.
    import time
    deadline = time.monotonic() + 3.0
    found = False
    while time.monotonic() < deadline:
        try:
            # Compare against user_channel_id since open_channel() returns
            # a UserChannelId, not the funding-tx channel_id.
            channel_ids = [str(c.user_channel_id) for c in node.list_channels()]
        except Exception:  # noqa: BLE001
            # If list_channels fails transiently, treat as "still pending"
            # and keep polling; we'll fall through to the not-found path if
            # the final poll also misses.
            channel_ids = []
        if ucid_str in channel_ids:
            found = True
            break
        time.sleep(0.25)

    if not found:
        # Channel vanished — look for the reason in the LDK log.
        # The channel_id in the log is the funding channel id (hex),
        # which differs from user_channel_id. Search all recent closes.
        reason = _parse_channel_rejection()
        from saturnzap.output import CommandError
        if reason:
            raise CommandError(
                "CHANNEL_REJECTED",
                f"Peer rejected the channel: {reason}",
            )
        raise CommandError(
            "CHANNEL_REJECTED",
            "Peer rejected the channel. Check 'sz status' and LDK logs "
            "for details.",
        )

    return ucid_str


def close_channel(channel_id: str, counterparty_node_id: str) -> None:
    """Cooperatively close a channel.

    Accepts either the funding-tx ``channel_id`` or LDK's numeric
    ``user_channel_id``. Resolves to the user_channel_id LDK requires.
    """
    if _use_ipc():
        _ipc(
            "close_channel",
            channel_id=channel_id,
            counterparty_node_id=counterparty_node_id,
        )
        return
    from saturnzap.output import CommandError
    n = _require_node()
    ucid = _resolve_user_channel_id(n, channel_id)
    if ucid is None:
        raise CommandError(
            "INVALID_CHANNEL_ID",
            f"No channel matches {channel_id!r}. Use 'sz channels list' "
            "to see channel_id / user_channel_id values.",
        )
    n.close_channel(ucid, counterparty_node_id)


def force_close_channel(
    channel_id: str, counterparty_node_id: str, reason: str | None = None,
) -> None:
    """Force-close a channel.

    Accepts either the funding-tx ``channel_id`` or LDK's numeric
    ``user_channel_id``.
    """
    if _use_ipc():
        _ipc(
            "force_close_channel",
            channel_id=channel_id, counterparty_node_id=counterparty_node_id,
            reason=reason,
        )
        return
    from saturnzap.output import CommandError
    n = _require_node()
    ucid = _resolve_user_channel_id(n, channel_id)
    if ucid is None:
        raise CommandError(
            "INVALID_CHANNEL_ID",
            f"No channel matches {channel_id!r}. Use 'sz channels list' "
            "to see channel_id / user_channel_id values.",
        )
    n.force_close_channel(ucid, counterparty_node_id, reason)
