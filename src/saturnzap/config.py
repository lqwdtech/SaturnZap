"""SaturnZap configuration — paths, defaults, TOML helpers."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import httpx
from platformdirs import user_config_dir, user_data_dir

APP_NAME = "saturnzap"

# Default network — always signet during development
DEFAULT_NETWORK = "signet"

VALID_NETWORKS = ("signet", "testnet", "bitcoin")

# Public signet Esplora endpoint
DEFAULT_ESPLORA_URL = "https://mempool.space/signet/api"

# Fallback Esplora endpoints per network.  Probed in order; first healthy wins.
ESPLORA_FALLBACKS: dict[str, list[str]] = {
    "signet": [
        "https://mempool.space/signet/api",
        "https://blockstream.info/signet/api",
    ],
    "testnet": [
        "https://mempool.space/testnet/api",
        "https://blockstream.info/testnet/api",
    ],
    "bitcoin": [
        "https://mempool.space/api",
        "https://blockstream.info/api",
    ],
}

# ── Active network (set by CLI --network or config) ──────────────

_active_network: str | None = None


def set_network(network: str) -> None:
    """Set the active network for this process (called by CLI --network)."""
    global _active_network  # noqa: PLW0603
    if network not in VALID_NETWORKS:
        msg = f"Invalid network '{network}'. Choose from: {', '.join(VALID_NETWORKS)}"
        raise ValueError(msg)
    _active_network = network


def get_network() -> str:
    """Return the active network: CLI override > config.toml > default."""
    if _active_network is not None:
        return _active_network
    cfg = _load_config_raw()
    return cfg.get("network", DEFAULT_NETWORK)


def resolve_esplora(network: str, config_override: str | None = None) -> str:
    """Return the best reachable Esplora URL for *network*.

    1. If *config_override* is set (user wrote ``esplora_url`` in config.toml),
       use it unconditionally — no probing.
    2. Otherwise probe each URL in ``ESPLORA_FALLBACKS[network]`` with a 3 s
       timeout on ``GET /blocks/tip/height``.
    3. If none respond, return the first URL anyway (LDK retries internally).
    """
    if config_override:
        return config_override

    urls = ESPLORA_FALLBACKS.get(network, ESPLORA_FALLBACKS["signet"])
    for url in urls:
        try:
            r = httpx.get(f"{url}/blocks/tip/height", timeout=3.0)
            if r.status_code == 200:
                return url
        except httpx.HTTPError:
            continue
    return urls[0]


def data_dir() -> Path:
    """Return the network-namespaced data directory, creating it if needed."""
    network = get_network()
    p = Path(user_data_dir(APP_NAME)) / network
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    """Return the OS-appropriate config directory, creating it if needed."""
    p = Path(user_config_dir(APP_NAME))
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    """Return the path to the main config TOML file."""
    return config_dir() / "config.toml"


def _load_config_raw() -> dict[str, Any]:
    """Load config TOML without triggering network resolution (avoids recursion)."""
    path = config_dir() / "config.toml"
    if path.exists():
        with open(path, "rb") as f:
            return tomllib.load(f)
    return {}


def load_config() -> dict[str, Any]:
    """Load config from TOML, returning defaults if the file doesn't exist."""
    raw = _load_config_raw()
    merged = _defaults()
    merged.update(raw)
    merged["network"] = get_network()
    return merged


def _defaults() -> dict[str, Any]:
    return {
        "network": DEFAULT_NETWORK,
        "esplora_url": DEFAULT_ESPLORA_URL,
    }


_LIQUIDITY_DEFAULTS: dict[str, Any] = {
    "outbound_threshold_percent": 20,
    "inbound_threshold_percent": 20,
    "auto_open_enabled": False,
}


def load_liquidity_config() -> dict[str, Any]:
    """Return the ``[liquidity]`` section from config, with defaults."""
    cfg = load_config()
    merged = dict(_LIQUIDITY_DEFAULTS)
    merged.update(cfg.get("liquidity", {}))
    return merged
