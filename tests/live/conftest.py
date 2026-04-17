"""Shared fixtures for live signet tests.

Live tests run against real SaturnZap nodes on DigitalOcean droplets.
They are skipped by default — use ``pytest -m live`` to run them.
"""

from __future__ import annotations

import os
import subprocess

import pytest

# Live test droplet hosts. Override via env vars so forks/contributors can
# point the live suite at their own infrastructure without editing source.
MAIN_DROPLET_HOST = os.environ.get("SZ_LIVE_MAIN_HOST", "")
PEER_DROPLET_HOST = os.environ.get("SZ_LIVE_PEER_HOST", "")


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
    skip = pytest.mark.skip(
        reason="Live test droplet not configured — set SZ_LIVE_MAIN_HOST"
    )
    if not MAIN_DROPLET_HOST:
        for item in items:
            if "live" in [m.name for m in item.iter_markers()]:
                item.add_marker(skip)
        return

    skip_unreachable = pytest.mark.skip(reason="Live test droplet not reachable")
    for item in items:
        if "live" in [m.name for m in item.iter_markers()]:
            # Quick connectivity check for the main droplet
            try:
                subprocess.run(  # noqa: S603
                    ["ssh", "-o", "ConnectTimeout=5",  # noqa: S607
                     f"root@{MAIN_DROPLET_HOST}", "echo ok"],
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
            except (  # noqa: E501
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                FileNotFoundError,
            ):
                item.add_marker(skip_unreachable)


@pytest.fixture()
def main_droplet():
    """SSH helper for the main SaturnZap droplet."""
    if not MAIN_DROPLET_HOST:
        pytest.skip("SZ_LIVE_MAIN_HOST not set")
    return _DropletSSH(MAIN_DROPLET_HOST)


@pytest.fixture()
def test_peer_droplet():
    """SSH helper for the test peer droplet."""
    if not PEER_DROPLET_HOST:
        pytest.skip("SZ_LIVE_PEER_HOST not set")
    return _DropletSSH(PEER_DROPLET_HOST)


class _DropletSSH:
    """Simple SSH command runner for droplet testing."""

    _SZ_BIN = "/root/saturnzap/.venv/bin/sz"

    def __init__(self, host: str):
        self.host = host

    def run(self, cmd: str, timeout: int = 30) -> str:
        """Run a command on the droplet and return stdout."""
        # Source /etc/environment for SZ_PASSPHRASE and other env vars
        wrapped = f"source /etc/environment 2>/dev/null; {cmd}"
        result = subprocess.run(  # noqa: S603
            ["ssh", "-o", "StrictHostKeyChecking=no",  # noqa: S607
             f"root@{self.host}", wrapped],
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
        out = self.run(f"{self._SZ_BIN} {args}", timeout=timeout)
        return json.loads(out)

    def start_daemon(self) -> None:
        """Start sz in daemon mode (background) so it listens on 9735."""
        self.run(
            f"nohup {self._SZ_BIN} start --daemon "
            "> /tmp/sz-daemon.log 2>&1 & sleep 3",
            timeout=15,
        )

    def stop_daemon(self) -> None:
        """Stop the sz daemon process."""
        import contextlib

        with contextlib.suppress(RuntimeError):
            self.run("pkill -f 'sz start --daemon'; sleep 1; true")


class _MainnetDropletSSH(_DropletSSH):
    """SSH command runner that always passes --network bitcoin."""

    def sz(self, args: str, timeout: int = 120) -> dict:
        """Run an sz --network bitcoin command and parse JSON output."""
        import json

        out = self.run(
            f"{self._SZ_BIN} --network bitcoin {args}",
            timeout=timeout,
        )
        return json.loads(out)

    def start_mainnet_daemon(self) -> None:
        """Start sz mainnet daemon so node stays warm across tests."""
        self.run(
            f"nohup {self._SZ_BIN} --network bitcoin start --daemon "
            "> /tmp/sz-mainnet-daemon.log 2>&1 & sleep 5",
            timeout=30,
        )

    def stop_mainnet_daemon(self) -> None:
        """Stop the mainnet daemon process."""
        import contextlib

        with contextlib.suppress(RuntimeError):
            self.run(
                f"{self._SZ_BIN} --network bitcoin stop; sleep 1; true"
            )


@pytest.fixture(scope="module")
def mainnet_droplet():
    """SSH helper for the main droplet with --network bitcoin.

    Starts a mainnet daemon before all tests in the module and stops
    it afterwards, so LDK doesn't cold-start on every command.
    """
    if not MAIN_DROPLET_HOST:
        pytest.skip("SZ_LIVE_MAIN_HOST not set")
    d = _MainnetDropletSSH(MAIN_DROPLET_HOST)
    d.start_mainnet_daemon()
    yield d
    d.stop_mainnet_daemon()
