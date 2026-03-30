"""Shared fixtures for live signet tests.

Live tests run against real SaturnZap nodes on DigitalOcean droplets.
They are skipped by default — use ``pytest -m live`` to run them.
"""

from __future__ import annotations

import subprocess

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless ``-m live`` is explicitly passed."""
    run_live = False
    for item in items:
        if "live" in [m.name for m in item.iter_markers()]:
            run_live = True
            break

    if not run_live:
        return

    # If we're here, user explicitly selected live tests — check connectivity
    skip = pytest.mark.skip(reason="Live test droplet not reachable")
    for item in items:
        if "live" in [m.name for m in item.iter_markers()]:
            # Quick connectivity check for the main droplet
            try:
                subprocess.run(
                    ["ssh", "-o", "ConnectTimeout=5",  # noqa: S607
                     "root@137.184.229.83", "echo ok"],
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
            except (  # noqa: E501
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                FileNotFoundError,
            ):
                item.add_marker(skip)


@pytest.fixture()
def main_droplet():
    """SSH helper for the main SaturnZap droplet."""
    return _DropletSSH("137.184.229.83")


@pytest.fixture()
def test_peer_droplet():
    """SSH helper for the test peer droplet."""
    return _DropletSSH("24.199.102.209")


class _DropletSSH:
    """Simple SSH command runner for droplet testing."""

    def __init__(self, host: str):
        self.host = host

    def run(self, cmd: str, timeout: int = 30) -> str:
        """Run a command on the droplet and return stdout."""
        result = subprocess.run(  # noqa: S603
            ["ssh", "-o", "StrictHostKeyChecking=no",  # noqa: S607
             f"root@{self.host}", cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(f"SSH command failed on {self.host}: {result.stderr}")
        return result.stdout.strip()

    def sz(self, args: str, timeout: int = 30) -> dict:
        """Run an sz command and parse JSON output."""
        import json
        out = self.run(f"sz {args}", timeout=timeout)
        return json.loads(out)
