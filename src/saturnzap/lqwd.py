"""LQWD Lightning node directory.

Placeholder entries — real signet pubkeys will be filled in once LQWD
publishes their signet fleet.  The structure and selection logic are real.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

# Each entry: region_code, alias, pubkey, host:port, utc_offset (hours)
# TODO: Replace pubkeys/addresses with real LQWD signet node details
NODES: list[dict] = [
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


def list_nodes(region: str | None = None) -> list[dict]:
    """Return LQWD nodes, optionally filtered by region code."""
    if region is None:
        return list(NODES)
    region_upper = region.upper()
    return [n for n in NODES if n["region"] == region_upper]


def _system_utc_offset_hours() -> float:
    """Return the system's current UTC offset in hours."""
    return datetime.now(UTC).astimezone().utcoffset().total_seconds() / 3600


def get_nearest() -> dict:
    """Return the LQWD node closest to the system's timezone.

    Override with the ``SZ_REGION`` environment variable to force a specific
    region (e.g. ``SZ_REGION=JP``).
    """
    override = os.environ.get("SZ_REGION", "").strip().upper()
    if override:
        matches = list_nodes(override)
        if matches:
            return matches[0]

    local_offset = _system_utc_offset_hours()
    return min(
        NODES,
        key=lambda n: abs(n["utc_offset"] - local_offset),
    )
