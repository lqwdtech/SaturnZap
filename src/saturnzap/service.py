"""Systemd service generator for persistent SaturnZap node."""
# ruff: noqa: S603, S607 — subprocess calls use hardcoded systemctl paths

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_UNIT_NAME = "saturnzap.service"
_UNIT_PATH = Path("/etc/systemd/system") / _UNIT_NAME

_UNIT_TEMPLATE = """\
[Unit]
Description=SaturnZap Lightning Node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={exec_start}
Restart=on-failure
RestartSec=10
User={user}
Environment=SZ_PASSPHRASE={passphrase_placeholder}
{env_line}
WorkingDirectory={work_dir}

[Install]
WantedBy=multi-user.target
"""


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

    Args:
        passphrase_env: If True, reads SZ_PASSPHRASE from current env.
    """
    user = os.environ.get("USER", "root")
    work_dir = os.getcwd()
    passphrase = os.environ.get("SZ_PASSPHRASE", "") if passphrase_env else ""

    # Collect extra env vars
    env_lines = []
    for var in ("SZ_REGION", "SZ_ESPLORA_URL", "SZ_MCP_MAX_SPEND_SATS"):
        val = os.environ.get(var)
        if val:
            env_lines.append(f"Environment={var}={val}")

    sz_path = _find_sz_executable()
    exec_start = f"{sz_path} start"

    return _UNIT_TEMPLATE.format(
        exec_start=exec_start,
        user=user,
        passphrase_placeholder=passphrase,
        env_line="\n".join(env_lines),
        work_dir=work_dir,
    )


def install() -> dict:
    """Write the systemd unit file and enable it."""
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

    subprocess.run(  # noqa: S603, S607
        ["systemctl", "daemon-reload"], check=True,
    )

    return {
        "unit_name": _UNIT_NAME,
        "message": "Service removed.",
    }


def status() -> dict:
    """Check service status via systemctl."""
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

    return {
        "unit_name": _UNIT_NAME,
        "is_active": is_active,
        "is_enabled": is_enabled,
        "installed": _UNIT_PATH.exists(),
    }
