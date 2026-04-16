"""Systemd service generator for persistent SaturnZap node."""
# ruff: noqa: S603, S607 — subprocess calls use hardcoded systemctl paths

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_UNIT_NAME = "saturnzap.service"
_UNIT_PATH = Path("/etc/systemd/system") / _UNIT_NAME
_ENV_DIR = Path("/etc/saturnzap")
_ENV_PATH = _ENV_DIR / "saturnzap.env"

_UNIT_TEMPLATE = """\
[Unit]
Description=SaturnZap Lightning Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStartPre=/usr/bin/test -f {seed_path}
ExecStart={exec_start}
Restart=on-failure
RestartSec=10
User={user}
EnvironmentFile={env_path}
Environment=SZ_MAINNET_CONFIRM=yes
WorkingDirectory={work_dir}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def _render_env_file(passphrase: str) -> str:
    """Render the EnvironmentFile contents with passphrase + extra vars."""
    lines = [f"SZ_PASSPHRASE={passphrase}"]
    for var in ("SZ_REGION", "SZ_ESPLORA_URL", "SZ_MCP_MAX_SPEND_SATS"):
        val = os.environ.get(var)
        if val:
            lines.append(f"{var}={val}")
    return "\n".join(lines) + "\n"


def _find_sz_executable() -> str:
    """Locate the sz CLI entrypoint."""
    sz = shutil.which("sz")
    if sz:
        return sz
    # Fallback: python -m saturnzap.cli approach
    import sys
    return f"{sys.executable} -m saturnzap.cli"


def generate_unit(passphrase_env: bool = True) -> str:
    """Generate the systemd unit file content.

    The passphrase is NOT embedded in the unit file. It is written to a
    separate EnvironmentFile with 0o600 permissions by install().

    Args:
        passphrase_env: Unused. Kept for backward compatibility.
    """
    del passphrase_env  # no longer embedded in unit
    user = os.environ.get("USER", "root")
    work_dir = os.getcwd()

    # Resolve the seed file path for ExecStartPre check
    from saturnzap.config import data_dir
    seed_path = str(data_dir() / "seed.enc")

    sz_path = _find_sz_executable()
    exec_start = f"{sz_path} start --daemon"

    return _UNIT_TEMPLATE.format(
        exec_start=exec_start,
        user=user,
        env_path=str(_ENV_PATH),
        work_dir=work_dir,
        seed_path=seed_path,
    )


def install() -> dict:
    """Write the systemd unit file, environment file, open firewall, enable."""
    # Validate passphrase is available before writing the unit
    passphrase = os.environ.get("SZ_PASSPHRASE", "")
    if not passphrase:
        from saturnzap import output
        output.error(
            "INVALID_ARGS",
            "SZ_PASSPHRASE must be set before installing the service. "
            "The service reads the passphrase from its EnvironmentFile.",
        )

    # Open firewall port for Lightning P2P
    from saturnzap.node import open_firewall_port
    firewall = open_firewall_port()

    # Write the EnvironmentFile (0o600 — contains passphrase) BEFORE the unit
    _ENV_DIR.mkdir(parents=True, exist_ok=True)
    _ENV_DIR.chmod(0o700)
    _ENV_PATH.write_text(_render_env_file(passphrase))
    _ENV_PATH.chmod(0o600)

    # Write the unit file — safe to be world-readable (no secrets inside)
    unit_content = generate_unit()
    _UNIT_PATH.write_text(unit_content)
    _UNIT_PATH.chmod(0o644)

    subprocess.run(  # noqa: S603, S607
        ["systemctl", "daemon-reload"], check=True,
    )
    subprocess.run(  # noqa: S603, S607
        ["systemctl", "enable", _UNIT_NAME], check=True,
    )
    subprocess.run(  # noqa: S603, S607
        ["systemctl", "start", _UNIT_NAME], check=True,
    )

    return {
        "unit_path": str(_UNIT_PATH),
        "unit_name": _UNIT_NAME,
        "firewall": firewall,
        "message": (
            "Service installed and started. "
            f"Check: systemctl status {_UNIT_NAME}"
        ),
    }


def uninstall() -> dict:
    """Stop, disable, and remove the systemd unit."""
    subprocess.run(  # noqa: S603, S607
        ["systemctl", "stop", _UNIT_NAME], check=False,
    )
    subprocess.run(  # noqa: S603, S607
        ["systemctl", "disable", _UNIT_NAME], check=False,
    )

    if _UNIT_PATH.exists():
        _UNIT_PATH.unlink()

    if _ENV_PATH.exists():
        _ENV_PATH.unlink()

    subprocess.run(  # noqa: S603, S607
        ["systemctl", "daemon-reload"], check=True,
    )

    return {
        "unit_name": _UNIT_NAME,
        "message": "Service removed.",
    }


def status() -> dict:
    """Check service status, port listening, and reachability."""
    result = subprocess.run(  # noqa: S603, S607
        ["systemctl", "is-active", _UNIT_NAME],
        capture_output=True, text=True, check=False,
    )
    is_active = result.stdout.strip() == "active"

    result2 = subprocess.run(  # noqa: S603, S607
        ["systemctl", "is-enabled", _UNIT_NAME],
        capture_output=True, text=True, check=False,
    )
    is_enabled = result2.stdout.strip() == "enabled"

    # Check if Lightning port is listening
    from saturnzap.config import DEFAULT_LISTEN_PORTS, get_network
    port = DEFAULT_LISTEN_PORTS.get(get_network(), 9735)
    port_listening = _is_port_listening(port)

    return {
        "unit_name": _UNIT_NAME,
        "is_active": is_active,
        "is_enabled": is_enabled,
        "installed": _UNIT_PATH.exists(),
        "port": port,
        "port_listening": port_listening,
    }


def _is_port_listening(port: int) -> bool:
    """Check if a port is listening locally via socket probe."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0
