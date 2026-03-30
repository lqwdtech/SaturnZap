"""Liquidity intelligence — channel health, recommendations, inbound requests."""

from __future__ import annotations

from saturnzap import lqwd, node, output
from saturnzap.config import load_liquidity_config


def _health_score(channel: dict) -> int:
    """Compute a 0–100 health score based on outbound/capacity ratio.

    A balanced channel has ~50% outbound.  Score drops toward 0 when
    the channel is fully depleted in either direction.
    """
    capacity = channel["channel_value_sats"]
    if capacity == 0:
        return 0
    outbound_sats = channel["outbound_capacity_msat"] // 1000
    ratio = outbound_sats / capacity
    # Score peaks at 50% outbound, drops linearly toward 0% or 100%
    return round(min(ratio, 1.0 - ratio) * 2 * 100)


def _health_label(score: int) -> str:
    """Map a 0–100 score to a human-readable label."""
    if score >= 40:
        return "healthy"
    if score >= 20:
        return "warning"
    return "critical"


def _generate_recommendations(
    channels: list[dict],
    balance: dict,
    cfg: dict,
) -> list[str]:
    """Return actionable recommendations based on channel state and thresholds."""
    recs: list[str] = []
    outbound_thresh = cfg.get("outbound_threshold_percent", 20)
    inbound_thresh = cfg.get("inbound_threshold_percent", 20)

    if not channels:
        recs.append(
            "No channels open. Open a channel to send/receive "
            "Lightning payments."
        )
        if balance.get("spendable_onchain_sats", 0) > 0:
            recs.append(
                "On-chain funds available. Use 'sz channels open' to create a channel."
            )
        return recs

    usable = [c for c in channels if c["is_usable"]]
    pending = [c for c in channels if not c["is_channel_ready"]]
    if pending:
        recs.append(
            f"{len(pending)} channel(s) awaiting confirmation — "
            "wait for on-chain blocks."
        )

    for ch in usable:
        cap = ch["channel_value_sats"]
        if cap == 0:
            continue
        outbound_pct = (ch["outbound_capacity_msat"] // 1000) / cap * 100
        inbound_pct = (ch["inbound_capacity_msat"] // 1000) / cap * 100

        peer = ch["counterparty_node_id"][:12]
        if outbound_pct < outbound_thresh:
            recs.append(
                f"Low outbound ({outbound_pct:.0f}%) on channel with {peer}… — "
                "consider opening a new channel or receiving payments."
            )
        if inbound_pct < inbound_thresh:
            recs.append(
                f"Low inbound ({inbound_pct:.0f}%) on channel with {peer}… — "
                "request inbound liquidity or spend some sats."
            )

    return recs


def get_status() -> dict:
    """Return a liquidity status report with per-channel health and recommendations."""
    balance = node.get_balance()
    channels = balance["channels"]
    cfg = load_liquidity_config()

    scored: list[dict] = []
    for ch in channels:
        score = _health_score(ch)
        scored.append({
            "channel_id": ch["channel_id"],
            "counterparty_node_id": ch["counterparty_node_id"],
            "channel_value_sats": ch["channel_value_sats"],
            "outbound_capacity_msat": ch["outbound_capacity_msat"],
            "inbound_capacity_msat": ch["inbound_capacity_msat"],
            "is_usable": ch["is_usable"],
            "health_score": score,
            "health_label": _health_label(score),
        })

    recs = _generate_recommendations(channels, balance, cfg)

    # Flag channels with offline peers (D2: stale channel detection)
    stale: list[dict] = []
    for ch in channels:
        if ch["is_channel_ready"] and not ch["is_usable"]:
            stale.append({
                "channel_id": ch["channel_id"],
                "counterparty_node_id": ch["counterparty_node_id"],
                "recommendation": (
                    "Peer offline — channel unusable. "
                    "Consider force-closing if persistent."
                ),
            })
    if stale:
        recs.append(
            f"{len(stale)} channel(s) have offline peers. "
            "Use 'sz channels close --force' if prolonged."
        )

    return {
        "channels": scored,
        "total_channels": len(scored),
        "usable_channels": sum(1 for c in scored if c["is_usable"]),
        "onchain_sats": balance["onchain_sats"],
        "lightning_sats": balance["lightning_sats"],
        "recommendations": recs,
        "stale_channels": stale,
    }


def request_inbound(
    amount_sats: int,
    region: str | None = None,
) -> dict:
    """Request inbound liquidity from an LQWD node.

    Currently implemented as a channel open with push_msat.
    TODO: Replace with LSPS2 JIT channel request when LQWD fleet supports it.
    """
    if region:
        nodes = lqwd.list_nodes(region)
        if not nodes:
            output.error(
                "UNKNOWN_REGION",
                f"No LQWD node in region '{region}'. "
                f"Available: {', '.join(n['region'] for n in lqwd.NODES)}",
            )
        target = nodes[0]
    else:
        target = lqwd.get_nearest()

    # Connect to the LQWD peer
    node.connect_peer(target["pubkey"], target["address"])

    # Open a channel pushing sats to the remote side to get inbound capacity.
    # The push amount is a fee we pay for the inbound — set at 1% minimum.
    push_sats = max(amount_sats // 100, 1000)
    channel_sats = amount_sats + push_sats

    ucid = node.open_channel(
        target["pubkey"],
        target["address"],
        channel_sats,
        push_msat=push_sats * 1000,
    )

    return {
        "user_channel_id": ucid,
        "lqwd_node": target["alias"],
        "lqwd_region": target["region"],
        "channel_capacity_sats": channel_sats,
        "inbound_sats": amount_sats,
        "fee_sats": push_sats,
        "message": (
            f"Inbound liquidity request sent to {target['alias']}. "
            "Channel will be usable after on-chain confirmation."
        ),
    }
