"""SaturnZap configuration — paths, defaults, TOML helpers."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import httpx
from platformdirs import user_config_dir, user_data_dir

APP_NAME = "saturnzap"

# Default network — mainnet for production use
DEFAULT_NETWORK = "bitcoin"

VALID_NETWORKS = ("signet", "testnet", "bitcoin")

# Default Lightning P2P listen port per network.
# Mainnet uses the standard Lightning port 9735; signet/testnet use adjacent
# ports to avoid bind conflicts when running multiple networks on one host.
DEFAULT_LISTEN_PORTS: dict[str, int] = {
    "signet": 9736,
    "testnet": 9737,
    "bitcoin": 9735,
}

# Public mainnet Esplora endpoint
DEFAULT_ESPLORA_URL = "https://esplora.lqwd.ai"

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
        "https://esplora.lqwd.ai",
        "https://blockstream.info/api",
        "https://mempool.space/api",
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
    """Return the active network: CLI flag > env var > config.toml > default."""
    if _active_network is not None:
        return _active_network
    env_net = os.environ.get("SZ_NETWORK")
    if env_net:
        if env_net not in VALID_NETWORKS:
            msg = (
                f"Invalid SZ_NETWORK '{env_net}'. "
                f"Choose from: {', '.join(VALID_NETWORKS)}"
            )
            raise ValueError(msg)
        return env_net
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

    env_url = os.environ.get("SZ_ESPLORA_URL")
    if env_url:
        return env_url

    urls = ESPLORA_FALLBACKS.get(network, ESPLORA_FALLBACKS["bitcoin"])
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


# ── Node section (alias, trusted peers, min_confirms, listen_port) ──

_NODE_DEFAULTS: dict[str, Any] = {
    "min_confirms": 3,
    # Channel announcement policy. "auto" probes the node's reachability and
    # announces only when the node looks reachable from the internet. "always"
    # forces announce on every open. "never" forces unannounced. Explicit
    # CLI/MCP flags override this.
    "announce_default": "auto",
}

VALID_ANNOUNCE_DEFAULTS = ("auto", "always", "never")


def load_node_config() -> dict[str, Any]:
    """Return the ``[node]`` section from config, with defaults."""
    cfg = _load_config_raw()
    merged = dict(_NODE_DEFAULTS)
    merged.update(cfg.get("node", {}))
    return merged


def save_node_config_key(key: str, value: Any) -> None:
    """Persist a single ``[node]`` key to ``config.toml``.

    Uses a minimal TOML writer — preserves existing top-level keys and the
    ``[node]`` / ``[liquidity]`` sections verbatim where possible.
    """
    path = config_path()
    raw: dict[str, Any] = _load_config_raw() if path.exists() else {}
    node_section = dict(raw.get("node", {}))
    if value is None:
        node_section.pop(key, None)
    else:
        node_section[key] = value
    raw["node"] = node_section
    _write_config_toml(raw)


def _write_config_toml(data: dict[str, Any]) -> None:
    """Serialise config dict to TOML. Simple writer (strings, ints, bools, lists)."""
    lines: list[str] = []
    top_scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    sections = {k: v for k, v in data.items() if isinstance(v, dict)}

    for k, v in top_scalars.items():
        lines.append(f"{k} = {_toml_value(v)}")
    for section_name, section in sections.items():
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[{section_name}]")
        for k, v in section.items():
            lines.append(f"{k} = {_toml_value(v)}")

    config_path().write_text("\n".join(lines) + "\n")


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    # string
    s = str(v).replace("\\", "\\\\").replace("\"", "\\\"")
    return f"\"{s}\""
