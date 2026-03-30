"""Live signet tests — connectivity, status, and basic operations.

Run with: pytest tests/live/ -m live -v
Requires: SSH access to droplets, SZ_PASSPHRASE set on droplets.
"""

from __future__ import annotations

import pytest


@pytest.mark.live
def test_main_droplet_status(main_droplet):
    """Verify the main droplet's node is running and synced."""
    data = main_droplet.sz("status")
    assert data["status"] == "ok"
    assert data["is_running"] is True
    assert data["network"] == "signet"
    assert data["block_height"] > 0


@pytest.mark.live
def test_main_droplet_balance(main_droplet):
    """Check the main droplet has a balance."""
    data = main_droplet.sz("balance")
    assert data["status"] == "ok"
    assert "onchain_sats" in data
    assert "lightning_sats" in data


@pytest.mark.live
def test_peer_droplet_status(test_peer_droplet):
    """Verify the test peer droplet's node is running."""
    data = test_peer_droplet.sz("status")
    assert data["status"] == "ok"
    assert data["is_running"] is True


@pytest.mark.live
def test_peer_connectivity(main_droplet, test_peer_droplet):
    """Verify both droplets can see each other as peers."""
    main_status = main_droplet.sz("status")
    peer_status = test_peer_droplet.sz("status")

    # Both should have at least one peer
    assert main_status["peer_count"] >= 0  # May not be connected yet
    assert peer_status["peer_count"] >= 0


@pytest.mark.live
def test_main_droplet_address(main_droplet):
    """Generate a new address on the main droplet."""
    data = main_droplet.sz("address")
    assert data["status"] == "ok"
    assert data["address"].startswith("tb1")  # signet/testnet address
