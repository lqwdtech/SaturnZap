"""LQWD Lightning node directory.

Mainnet entries sourced from lqwd.ai/contracts.json (2026-03-13).
Signet entries are placeholders — LQWD does not yet publish a signet fleet.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from saturnzap.config import get_network

# Each entry: region_code, alias, pubkey, host:port, utc_offset (hours)

MAINNET_NODES: list[dict] = [
    {
        "region": "CA",
        "alias": "LQwD-Canada",
        "pubkey": "0364913d18a19c671bb36dd04d6ad5be0fe8f2894314c36a9db3f03c2d414907e1",
        "address": "192.243.215.102:9735",
        "utc_offset": -5,
    },
    {
        "region": "US",
        "alias": "LQwD-US-West-2",
        "pubkey": "036afe432cad4fd5a5671d9d95d3d3671e315825efdc10f734dba1f47a711a276b",
        "address": "52.39.139.30:9735",
        "utc_offset": -8,
    },
    {
        "region": "BR",
        "alias": "LQWD-Brazil",
        "pubkey": "02c4ad243f18d8ed3a40e98725bc6a795b941d7e3d64be9f7dab38144f1eb09cb8",
        "address": "54.232.36.250:9735",
        "utc_offset": -3,
    },
    {
        "region": "GB",
        "alias": "LQWD-England",
        "pubkey": "02be8a325c61af50aebc2004e3a3db0dc8d255f2fb95036738392172f739fa1c3a",
        "address": "18.133.176.219:9735",
        "utc_offset": 0,
    },
    {
        "region": "IE",
        "alias": "LQWD-Ireland",
        "pubkey": "0230b207b3385feddb1ed18d5c7a808015aeb668aaf9bf980bee62465a382112c1",
        "address": "52.17.5.198:9735",
        "utc_offset": 0,
    },
    {
        "region": "FR",
        "alias": "LQWD-France",
        "pubkey": "032ae3168ba52314da581d6b6693c562b437a9cf805933d4d69e7801547e07302e",
        "address": "13.37.62.86:9735",
        "utc_offset": 1,
    },
    {
        "region": "DE",
        "alias": "LQWD-Germany",
        "pubkey": "032c9c7648e471befa2dc2d093e0854dd138f2718c0ad93bd4411328b33d072918",
        "address": "3.68.244.94:26000",
        "utc_offset": 1,
    },
    {
        "region": "IT",
        "alias": "LQWD-Italy",
        "pubkey": "0313827390afcae8876dc7d56c417d5698effb237e6eab45a364ac71e9e2044c9a",
        "address": "15.160.13.112:9735",
        "utc_offset": 1,
    },
    {
        "region": "SE",
        "alias": "LQwD-Sweden",
        "pubkey": "032312e5e15e89211df36e473d76af60672e3efebfe42a9b2113acbb456050b502",
        "address": "16.170.28.230:9735",
        "utc_offset": 1,
    },
    {
        "region": "ZA",
        "alias": "LQwD-SouthAfrica",
        "pubkey": "036fc6041f67b673e9357118eb2b74cb71aebf7e1e3535edcdba3b808b2a790c0a",
        "address": "13.245.58.129:9735",
        "utc_offset": 2,
    },
    {
        "region": "BH",
        "alias": "LQwD-Bahrain",
        "pubkey": "0390b3d73a0e40a1a4d91d486f422bcb232868000a05cf4d88d74b62a6e7421f18",
        "address": "157.175.240.136:9735",
        "utc_offset": 3,
    },
    {
        "region": "IN",
        "alias": "LQWD-India",
        "pubkey": "02b20c736785ce8e801d50ae0bb6f6daa534a992445b44f4b6255ebedebd84c037",
        "address": "3.111.151.70:9735",
        "utc_offset": 5,
    },
    {
        "region": "SG",
        "alias": "LQWD-Singapore",
        "pubkey": "026756a68c3437bdcdff8f43585db665fdd9585d082f4624d51bd0346bc396a73e",
        "address": "172.218.94.52:9735",
        "utc_offset": 8,
    },
    {
        "region": "HK",
        "alias": "LQwD-HongKong",
        "pubkey": "02eb9dfcbe445ea0366635e932db3bf78e95eb5241ba9bd3f1c72b48fa9f3fc234",
        "address": "18.163.90.95:9735",
        "utc_offset": 8,
    },
    {
        "region": "ID",
        "alias": "LQWD-Indonesia",
        "pubkey": "02b1afba6153f9668ea0be12f4dbfc396a782a52d3eccf868732a1088eb2cc5d69",
        "address": "108.136.185.66:9735",
        "utc_offset": 7,
    },
    {
        "region": "KR",
        "alias": "LQWD-SouthKorea",
        "pubkey": "036982a2b2398b9835a9d6cd2371a08c6e221f9e1b879008959dae28413af78067",
        "address": "3.39.44.50:9735",
        "utc_offset": 9,
    },
    {
        "region": "JP",
        "alias": "LQwD-Japan",
        "pubkey": "031a01e29587952eda0ed5d10c4e79bf0fc88d61aeae89e8a7ea7c036badb8c793",
        "address": "35.77.235.168:9735",
        "utc_offset": 9,
    },
    {
        "region": "AU",
        "alias": "LQWD-Australia",
        "pubkey": "03e4f3d7ccf98bdbf24085b948f204a6c0c0b4464a7572cbac85c746085b14bbc9",
        "address": "13.211.49.49:9735",
        "utc_offset": 10,
    },
]

# Signet placeholders — LQWD does not yet publish signet nodes
SIGNET_NODES: list[dict] = [
    {
        "region": "CA",
        "alias": "LQWD-Canada",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000001",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": -5,
    },
    {
        "region": "US",
        "alias": "LQWD-US",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000002",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": -6,
    },
    {
        "region": "BR",
        "alias": "LQWD-Brazil",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000003",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": -3,
    },
    {
        "region": "GB",
        "alias": "LQWD-UK",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000004",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 0,
    },
    {
        "region": "IE",
        "alias": "LQWD-Ireland",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000005",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 0,
    },
    {
        "region": "FR",
        "alias": "LQWD-France",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000006",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 1,
    },
    {
        "region": "DE",
        "alias": "LQWD-Germany",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000007",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 1,
    },
    {
        "region": "IT",
        "alias": "LQWD-Italy",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000008",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 1,
    },
    {
        "region": "SE",
        "alias": "LQWD-Sweden",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000009",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 1,
    },
    {
        "region": "ZA",
        "alias": "LQWD-SouthAfrica",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000010",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 2,
    },
    {
        "region": "BH",
        "alias": "LQWD-Bahrain",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000011",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 3,
    },
    {
        "region": "IN",
        "alias": "LQWD-India",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000012",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 5,
    },
    {
        "region": "SG",
        "alias": "LQWD-Singapore",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000013",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 8,
    },
    {
        "region": "HK",
        "alias": "LQWD-HongKong",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000014",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 8,
    },
    {
        "region": "ID",
        "alias": "LQWD-Indonesia",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000015",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 7,
    },
    {
        "region": "KR",
        "alias": "LQWD-Korea",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000016",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 9,
    },
    {
        "region": "JP",
        "alias": "LQWD-Japan",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000017",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 9,
    },
    {
        "region": "AU",
        "alias": "LQWD-Australia",
        "pubkey": "000000000000000000000000000000000000000000000000000000000000000018",
        "address": "placeholder.lqwd.ai:9735",
        "utc_offset": 10,
    },
]

# Backward-compat alias — tests and code that reference NODES directly
NODES = SIGNET_NODES


# Additional LQWD mainnet infrastructure pubkeys that aren't in MAINNET_NODES.
# Primary LND node (used by LQWDClaw faucet to open inbound channels).
LQWD_MAINNET_LND_PUBKEYS: list[str] = [
    "03683cdb57591430a24ce0fe86c966b2cc396cf3025a7bbac6683a23873f24758c",  # noqa: E501  # pragma: allowlist secret
]


def mainnet_trusted_pubkeys() -> list[str]:
    """Return all LQWD mainnet pubkeys used for anchor reserve waivers.

    Combines the 18-region CLN fleet (``MAINNET_NODES``) with the primary LND
    pubkey used by the LQWDClaw faucet. Used to populate LDK Node's
    ``anchor_channels_config.trusted_peers_no_reserve`` so fresh zero-balance
    wallets can accept inbound channels from any LQWD node without needing an
    on-chain reserve.
    """
    fleet = [n["pubkey"] for n in MAINNET_NODES]
    # De-duplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for pk in fleet + LQWD_MAINNET_LND_PUBKEYS:
        if pk not in seen:
            seen.add(pk)
            out.append(pk)
    return out


def _nodes_for_network() -> list[dict]:
    """Return the node list for the active network."""
    network = get_network()
    if network == "bitcoin":
        return MAINNET_NODES
    return SIGNET_NODES


def list_nodes(region: str | None = None) -> list[dict]:
    """Return LQWD nodes, optionally filtered by region code."""
    nodes = _nodes_for_network()
    if region is None:
        return list(nodes)
    region_upper = region.upper()
    return [n for n in nodes if n["region"] == region_upper]


def _system_utc_offset_hours() -> float:
    """Return the system's current UTC offset in hours."""
    return datetime.now(UTC).astimezone().utcoffset().total_seconds() / 3600


def get_nearest() -> dict:
    """Return the LQWD node closest to the system's timezone.

    Override with the ``SZ_REGION`` environment variable to force a specific
    region (e.g. ``SZ_REGION=JP``).
    """
    nodes = _nodes_for_network()
    override = os.environ.get("SZ_REGION", "").strip().upper()
    if override:
        matches = [n for n in nodes if n["region"] == override]
        if matches:
            return matches[0]

    local_offset = _system_utc_offset_hours()
    return min(
        nodes,
        key=lambda n: abs(n["utc_offset"] - local_offset),
    )
