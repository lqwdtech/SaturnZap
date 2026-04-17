"""Live tests — connectivity, status, and basic operations.

Run with: pytest tests/live/ -m live -v
Requires: SSH access to droplets, SZ_PASSPHRASE set on droplets.
Works on any network (signet, bitcoin, testnet).
"""

from __future__ import annotations

import pytest

# ── Status & health ──────────────────────────────────────────────


@pytest.mark.live
def test_main_droplet_status(main_droplet):
    """Verify the main droplet's node is running and synced."""
    data = main_droplet.sz("status")
    assert data["status"] == "ok"
    assert data["is_running"] is True
    assert data["network"] in ("bitcoin", "signet", "testnet")
    assert data["block_height"] > 0
    assert len(data["pubkey"]) == 66  # compressed pubkey hex


@pytest.mark.live
def test_peer_droplet_status(test_peer_droplet):
    """Verify the test peer droplet's node is running."""
    data = test_peer_droplet.sz("status")
    assert data["status"] == "ok"
    assert data["is_running"] is True
    assert data["network"] in ("bitcoin", "signet", "testnet")
    assert data["block_height"] > 0


@pytest.mark.live
def test_both_nodes_synced_to_same_height(main_droplet, test_peer_droplet):
    """Both nodes should be within 2 blocks of each other."""
    main = main_droplet.sz("status")
    peer = test_peer_droplet.sz("status")
    assert abs(main["block_height"] - peer["block_height"]) <= 2


# ── Balance ──────────────────────────────────────────────────────


@pytest.mark.live
def test_main_droplet_balance(main_droplet):
    """Main droplet should return a valid balance structure."""
    data = main_droplet.sz("balance")
    assert data["status"] == "ok"
    assert isinstance(data["onchain_sats"], int)
    assert isinstance(data["lightning_sats"], int)
    assert isinstance(data["spendable_onchain_sats"], int)
    assert "channels" in data


@pytest.mark.live
def test_peer_droplet_balance(test_peer_droplet):
    """Peer droplet should return a valid balance structure."""
    data = test_peer_droplet.sz("balance")
    assert data["status"] == "ok"
    assert isinstance(data["onchain_sats"], int)


# ── Address generation ───────────────────────────────────────────


@pytest.mark.live
def test_main_droplet_address(main_droplet):
    """Generate a new address on the main droplet."""
    data = main_droplet.sz("address")
    assert data["status"] == "ok"
    # bech32 prefix depends on network: bc1 (mainnet), tb1 (signet/testnet)
    assert data["address"].startswith(("bc1", "tb1"))
    assert data["network"] in ("bitcoin", "signet", "testnet")


@pytest.mark.live
def test_address_changes_each_call(main_droplet):
    """Each address call should return a fresh address."""
    addr1 = main_droplet.sz("address")["address"]
    addr2 = main_droplet.sz("address")["address"]
    assert addr1 != addr2


# ── Peers ────────────────────────────────────────────────────────


@pytest.mark.live
def test_peers_list_returns_valid_json(main_droplet):
    """Peers list should return valid JSON with 'peers' array."""
    data = main_droplet.sz("peers list")
    assert data["status"] == "ok"
    assert isinstance(data["peers"], list)


@pytest.mark.live
def test_peer_connect_and_disconnect(main_droplet, test_peer_droplet):
    """Connect main to peer, verify, then disconnect.

    Both nodes must run simultaneously for peer connections.
    Starts the peer as a daemon, then runs a single-process script
    on the main that holds the node alive for connect → list → disconnect.
    """
    import json
    import textwrap

    # Get peer pubkey (per-command, daemon not running)
    peer_status = test_peer_droplet.sz("status")
    peer_pubkey = peer_status["pubkey"]

    # Write a test script to the main droplet
    peer_host = test_peer_droplet.host
    script = textwrap.dedent(f"""\
        import json, time, sys
        sys.path.insert(0, "/root/saturnzap/src")
        from saturnzap import node
        n = node._require_node()
        node.connect_peer("{peer_pubkey}", "{peer_host}:9735")
        time.sleep(2)
        peers = node.list_peers()
        print(json.dumps(peers))
        node.disconnect_peer("{peer_pubkey}")
        node.stop()
    """)

    # Start peer daemon so it listens on 9735
    test_peer_droplet.start_daemon()
    try:
        # Upload and run the script on main droplet
        main_droplet.run(
            f"cat > /tmp/sz_peer_test.py << 'SCRIPT_EOF'\n"
            f"{script}SCRIPT_EOF"
        )
        raw = main_droplet.run(
            "/root/saturnzap/.venv/bin/python /tmp/sz_peer_test.py",
            timeout=30,
        )
        peers = json.loads(raw)
        peer_ids = [p["node_id"] for p in peers]
        assert peer_pubkey in peer_ids
    finally:
        test_peer_droplet.stop_daemon()


# ── Channels ─────────────────────────────────────────────────────


@pytest.mark.live
def test_channels_list(main_droplet):
    """Channels list should return valid JSON."""
    data = main_droplet.sz("channels list")
    assert data["status"] == "ok"
    assert isinstance(data["channels"], list)


@pytest.mark.live
def test_peer_has_existing_channel(test_peer_droplet):
    """Peer droplet should have at least one channel."""
    data = test_peer_droplet.sz("balance")
    assert len(data["channels"]) >= 1
    ch = data["channels"][0]
    assert "channel_id" in ch
    assert "channel_value_sats" in ch
    assert ch["is_channel_ready"] is True


# ── Transactions ─────────────────────────────────────────────────


@pytest.mark.live
def test_transactions_list(main_droplet):
    """Transaction list should return valid JSON."""
    data = main_droplet.sz("transactions --limit 5")
    assert data["status"] == "ok"
    assert isinstance(data["transactions"], list)


# ── Invoice creation ─────────────────────────────────────────────


@pytest.mark.live
def test_create_and_verify_invoice(main_droplet):
    """Create an invoice and verify it has the expected fields."""
    data = main_droplet.sz(
        "invoice --amount-sats 100 --memo 'live-test'"
    )
    assert data["status"] == "ok"
    assert "invoice" in data
    assert "payment_hash" in data
    assert data["invoice"].startswith("lntbs")  # signet bolt11 prefix


# ── Payment with preimage ────────────────────────────────────────


@pytest.mark.live
def test_pay_invoice_returns_preimage(main_droplet, test_peer_droplet):
    """Pay between two signet nodes and verify preimage is returned.

    Peer creates an invoice, main pays it.  The response must include a
    non-null ``preimage`` string (hex, 64 chars).
    """
    import json
    import textwrap

    # Start peer daemon on signet so it can receive the payment
    test_peer_droplet.run(
        f"nohup {test_peer_droplet._SZ_BIN} --network signet "
        "start --daemon > /tmp/sz-daemon.log 2>&1 & sleep 5",
        timeout=20,
    )
    try:
        # Get peer pubkey (via daemon IPC)
        peer_status = test_peer_droplet.sz("--network signet status")
        peer_pubkey = peer_status["pubkey"]

        # Create invoice on peer (via daemon IPC)
        inv_data = test_peer_droplet.sz(
            "--network signet invoice --amount-sats 1 "
            "--memo 'preimage-test'"
        )
        assert inv_data["status"] == "ok"
        bolt11 = inv_data["invoice"]

        # Pay from main via an in-process script (node must be alive)
        peer_host = test_peer_droplet.host
        script = textwrap.dedent(f"""\
            import json, os, sys, time
            os.environ["SZ_NETWORK"] = "signet"
            sys.path.insert(0, "/root/saturnzap/src")
            from saturnzap import node, payments
            n = node._require_node()
            try:
                node.connect_peer("{peer_pubkey}", "{peer_host}:9735")
            except Exception:
                pass
            time.sleep(2)
            result = payments.pay_invoice("{bolt11}")
            print(json.dumps(result))
            node.stop()
        """)
        main_droplet.run(
            f"cat > /tmp/sz_pay_test.py << 'SCRIPT_EOF'\n"
            f"{script}SCRIPT_EOF"
        )
        raw = main_droplet.run(
            "/root/saturnzap/.venv/bin/python /tmp/sz_pay_test.py",
            timeout=60,
        )
        result = json.loads(raw)
        assert "preimage" in result
        assert result["preimage"] is not None
        assert len(result["preimage"]) == 64  # 32 bytes hex
    finally:
        test_peer_droplet.stop_daemon()


# ── Daemon shutdown via IPC ──────────────────────────────────────


@pytest.mark.live
def test_daemon_stop_via_ipc(main_droplet):
    """Start daemon, then ``sz stop`` should shut it down via IPC.

    Verifies that the daemon process actually exits (no leftover pid).
    """
    import time

    # Start daemon on main droplet
    main_droplet.start_daemon()
    time.sleep(2)

    # Capture the daemon PID before stopping
    pid_out = main_droplet.run(
        "pgrep -f 'sz.*start.*--daemon' | head -1"
    )
    daemon_pid = pid_out.strip()
    assert daemon_pid, "Daemon did not start"

    # Verify daemon is running (sz status succeeds via IPC)
    status = main_droplet.sz("status")
    assert status["status"] == "ok"
    assert status["is_running"] is True

    # Stop via sz stop (routes through IPC shutdown)
    stop_result = main_droplet.sz("stop")
    assert stop_result["status"] == "ok"

    # Wait for process to exit
    time.sleep(5)

    # Verify the specific daemon PID is gone
    try:
        cmd = f"kill -0 {daemon_pid} 2>&1 && echo alive || echo dead"
        alive = main_droplet.run(cmd)
    except RuntimeError:
        alive = "dead"
    assert "dead" in alive, f"Daemon PID {daemon_pid} still alive"
