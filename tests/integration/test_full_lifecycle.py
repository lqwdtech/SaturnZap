"""Integration test — full wallet lifecycle.

init -> setup -> address -> balance -> status -> stop.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from typer.testing import CliRunner

from saturnzap.cli import app

runner = CliRunner()


def test_full_lifecycle(monkeypatch, mock_node):
    """Walk through the complete first-run lifecycle and verify JSON at each step."""
    monkeypatch.setenv("SZ_PASSPHRASE", "lifecycle-test")

    # Step 1: setup --auto
    with (
        patch("saturnzap.node.build_node", return_value=mock_node),
        patch("saturnzap.liquidity.request_inbound", return_value={"channel": "ok"}),
    ):
        result = runner.invoke(app, ["setup", "--auto"])
    assert result.exit_code == 0
    setup_data = json.loads(result.output)
    assert setup_data["status"] == "ok"
    pubkey = setup_data["pubkey"]

    # Step 2: address
    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, ["address"])
    assert result.exit_code == 0
    addr_data = json.loads(result.output)
    assert addr_data["status"] == "ok"
    assert "address" in addr_data

    # Step 3: balance
    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, ["balance"])
    assert result.exit_code == 0
    bal_data = json.loads(result.output)
    assert bal_data["status"] == "ok"
    assert bal_data["onchain_sats"] == 100_000

    # Step 4: status
    with (
        patch("saturnzap.node._require_node", return_value=mock_node),
        patch("time.time", return_value=1010),
    ):
        result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    status_data = json.loads(result.output)
    assert status_data["status"] == "ok"
    assert status_data["pubkey"] == pubkey

    # Step 5: stop
    with patch("saturnzap.node._require_node", return_value=mock_node):
        result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0
    stop_data = json.loads(result.output)
    assert stop_data["status"] == "ok"


def test_setup_then_backup_then_restore(tmp_path, monkeypatch, mock_node):
    """setup → backup → delete seed → restore → verify mnemonic recoverable."""
    monkeypatch.setenv("SZ_PASSPHRASE", "backup-test")

    # Setup
    with (
        patch("saturnzap.node.build_node", return_value=mock_node),
        patch("saturnzap.liquidity.request_inbound", return_value={"channel": "ok"}),
    ):
        result = runner.invoke(app, ["setup", "--auto"])
    assert result.exit_code == 0

    # Backup
    backup_path = str(tmp_path / "lifecycle-backup.json")
    result = runner.invoke(app, ["backup", "--output", backup_path])
    assert result.exit_code == 0
    backup_data = json.loads(result.output)
    assert backup_data["status"] == "ok"

    # Delete seed
    from saturnzap import keystore
    keystore.seed_path().unlink()
    keystore.salt_path().unlink()
    assert not keystore.is_initialized()

    # Restore
    result = runner.invoke(app, ["restore", "--input", backup_path])
    assert result.exit_code == 0
    restore_data = json.loads(result.output)
    assert restore_data["status"] == "ok"

    # Verify wallet is back
    assert keystore.is_initialized()
