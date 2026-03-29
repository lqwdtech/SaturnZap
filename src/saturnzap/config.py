"""SaturnZap configuration — paths, defaults, TOML helpers."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "saturnzap"

# Default network — always signet during development
DEFAULT_NETWORK = "signet"

# Public signet Esplora endpoint
DEFAULT_ESPLORA_URL = "https://mempool.space/signet/api"


def data_dir() -> Path:
    """Return the OS-appropriate data directory, creating it if needed."""
    p = Path(user_data_dir(APP_NAME))
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


def load_config() -> dict[str, Any]:
    """Load config from TOML, returning defaults if the file doesn't exist."""
    path = config_path()
    if path.exists():
        with open(path, "rb") as f:
            return tomllib.load(f)
    return _defaults()


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
