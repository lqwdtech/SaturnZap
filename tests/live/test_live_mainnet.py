"""Mainnet live tests — read-only operations only, no real sats spent.

Run with: pytest tests/live/test_live_mainnet.py -m mainnet -v
Requires: SSH access to main droplet, mainnet wallet initialized.
"""

from __future__ import annotations

import pytest

# All tests in this module require both live droplet access and mainnet
pytestmark = [pytest.mark.live, pytest.mark.mainnet]

# ── Status ───────────────────────────────────────────────────────


def test_mainnet_status(mainnet_droplet):
    """Node reports network=bitcoin and is synced."""
    data = mainnet_droplet.sz("status")
    assert data["status"] == "ok"
    assert data["network"] == "bitcoin"
    assert data["is_running"] is True
    assert data["block_height"] > 0
    assert len(data["pubkey"]) == 66  # compressed pubkey hex


def test_mainnet_block_height_reasonable(mainnet_droplet):
    """Block height should be above 800k (mainnet in 2025+)."""
    data = mainnet_droplet.sz("status")
    assert data["block_height"] > 800_000


# ── Balance ──────────────────────────────────────────────────────


def test_mainnet_balance(mainnet_droplet):
    """Balance JSON has the correct structure (no sats expected)."""
    data = mainnet_droplet.sz("balance")
    assert data["status"] == "ok"
    assert isinstance(data["onchain_sats"], int)
    assert isinstance(data["lightning_sats"], int)
    assert isinstance(data["spendable_onchain_sats"], int)
    assert "channels" in data


def test_mainnet_balance_zero(mainnet_droplet):
    """Fresh mainnet wallet should have zero balance."""
    data = mainnet_droplet.sz("balance")
    assert data["onchain_sats"] == 0
    assert data["lightning_sats"] == 0


# ── Address ──────────────────────────────────────────────────────


def test_mainnet_address(mainnet_droplet):
    """Mainnet address should have bc1 prefix (not tb1)."""
    data = mainnet_droplet.sz("address")
    assert data["status"] == "ok"
    assert data["address"].startswith("bc1")
    assert data["network"] == "bitcoin"


def test_mainnet_address_unique(mainnet_droplet):
    """Each call should produce a different address."""
    addr1 = mainnet_droplet.sz("address")["address"]
    addr2 = mainnet_droplet.sz("address")["address"]
    assert addr1 != addr2


# ── Peers ────────────────────────────────────────────────────────


def test_mainnet_peers_list(mainnet_droplet):
    """Peers list returns valid JSON structure."""
    data = mainnet_droplet.sz("peers list")
    assert data["status"] == "ok"
    assert isinstance(data["peers"], list)


# ── Channels ─────────────────────────────────────────────────────


def test_mainnet_channels_list(mainnet_droplet):
    """Channels list returns valid JSON (empty is fine)."""
    data = mainnet_droplet.sz("channels list")
    assert data["status"] == "ok"
    assert isinstance(data["channels"], list)


# ── Invoice ──────────────────────────────────────────────────────


def test_mainnet_invoice_create(mainnet_droplet):
    """Mainnet invoice should use lnbc prefix (not lntbs)."""
    data = mainnet_droplet.sz(
        'invoice --amount-sats 1000 --memo "mainnet test"'
    )
    assert data["status"] == "ok"
    assert data["invoice"].startswith("lnbc")
    assert not data["invoice"].startswith("lntbs")
    assert data["amount_sats"] == 1000


# ── Liquidity ────────────────────────────────────────────────────


def test_mainnet_liquidity_status(mainnet_droplet):
    """Liquidity status returns valid structure."""
    data = mainnet_droplet.sz("liquidity status")
    assert data["status"] == "ok"
    assert isinstance(data["channels"], list)
    assert isinstance(data["total_channels"], int)


# ── Transactions ─────────────────────────────────────────────────


def test_mainnet_transactions(mainnet_droplet):
    """Transactions endpoint returns valid structure."""
    data = mainnet_droplet.sz("transactions --limit 10")
    assert data["status"] == "ok"
    assert isinstance(data["transactions"], list)
    assert isinstance(data["count"], int)
