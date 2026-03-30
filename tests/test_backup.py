"""Tests for saturnzap.backup — encrypted wallet backup and restore."""

from __future__ import annotations

import json

import pytest

from saturnzap import backup, keystore


@pytest.fixture(autouse=True)
def _clean_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("SZ_PASSPHRASE", "testpass")


@pytest.fixture()
def initialized_wallet():
    """Create an initialized wallet with a known mnemonic."""
    mnemonic = keystore.generate_mnemonic()
    keystore.save_encrypted(mnemonic, "testpass")
    return mnemonic


# ── backup ───────────────────────────────────────────────────────


def test_backup_creates_file(tmp_path, initialized_wallet):
    out = tmp_path / "backup.json"
    result = backup.backup(out, "testpass")

    assert out.exists()
    assert result["backup_path"] == str(out)
    assert result["format_version"] == 1
    assert result["has_l402_tokens"] is False  # No tokens cached yet


def test_backup_file_is_valid_json(tmp_path, initialized_wallet):
    out = tmp_path / "backup.json"
    backup.backup(out, "testpass")

    data = json.loads(out.read_text())
    assert data["saturnzap_backup"] is True
    assert data["format_version"] == 1
    assert "salt" in data
    assert "data" in data


def test_backup_file_permissions(tmp_path, initialized_wallet):
    out = tmp_path / "backup.json"
    backup.backup(out, "testpass")

    mode = oct(out.stat().st_mode & 0o777)
    assert mode == "0o600"


def test_backup_fails_no_seed(tmp_path):
    out = tmp_path / "backup.json"
    with pytest.raises(SystemExit):
        backup.backup(out, "testpass")


def test_backup_includes_l402_tokens(tmp_path, initialized_wallet):
    """Backup should include L402 token cache if present."""
    from saturnzap.config import data_dir
    token_dir = data_dir() / "l402_tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "abc123").write_text("LSAT mac:pre")

    out = tmp_path / "backup.json"
    result = backup.backup(out, "testpass")
    assert result["has_l402_tokens"] is True


# ── restore ──────────────────────────────────────────────────────


def test_restore_round_trip(tmp_path, initialized_wallet):
    """backup → delete seed → restore → verify mnemonic matches."""
    out = tmp_path / "backup.json"
    backup.backup(out, "testpass")

    # Delete seed
    keystore.seed_path().unlink()
    keystore.salt_path().unlink()
    assert not keystore.is_initialized()

    # Restore
    result = backup.restore(out, "testpass")
    assert result["restored"] is True

    # Verify mnemonic
    recovered = keystore.load_mnemonic("testpass")
    assert recovered == initialized_wallet


def test_restore_wrong_passphrase(tmp_path, initialized_wallet):
    out = tmp_path / "backup.json"
    backup.backup(out, "testpass")

    keystore.seed_path().unlink()
    keystore.salt_path().unlink()

    with pytest.raises(SystemExit):
        backup.restore(out, "wrong-password")


def test_restore_corrupt_file(tmp_path):
    bad = tmp_path / "corrupt.json"
    bad.write_text("not json at all")

    with pytest.raises(SystemExit):
        backup.restore(bad, "testpass")


def test_restore_not_a_backup(tmp_path):
    fake = tmp_path / "fake.json"
    fake.write_text('{"foo": "bar"}')

    with pytest.raises(SystemExit):
        backup.restore(fake, "testpass")


def test_restore_missing_file(tmp_path):
    with pytest.raises(SystemExit):
        backup.restore(tmp_path / "nonexistent.json", "testpass")


def test_restore_existing_wallet_blocked(tmp_path, initialized_wallet):
    """Restore should refuse if wallet already exists."""
    out = tmp_path / "backup.json"
    backup.backup(out, "testpass")

    # Don't delete seed — restore should fail
    with pytest.raises(SystemExit):
        backup.restore(out, "testpass")


def test_restore_l402_tokens(tmp_path, initialized_wallet):
    """Backup with L402 tokens → restore → verify tokens restored."""
    from saturnzap.config import data_dir
    token_dir = data_dir() / "l402_tokens"
    token_dir.mkdir(parents=True, exist_ok=True)
    (token_dir / "tok1").write_text("LSAT mac1:pre1")
    (token_dir / "tok2").write_text("LSAT mac2:pre2")

    out = tmp_path / "backup.json"
    backup.backup(out, "testpass")

    # Delete everything
    keystore.seed_path().unlink()
    keystore.salt_path().unlink()
    import shutil
    shutil.rmtree(token_dir)

    result = backup.restore(out, "testpass")
    assert result["restored_l402_tokens"] == 2

    # Verify tokens exist
    assert (data_dir() / "l402_tokens" / "tok1").read_text() == "LSAT mac1:pre1"


def test_restore_version_mismatch(tmp_path, initialized_wallet):
    """Backup with future format version should be rejected."""
    out = tmp_path / "backup.json"
    backup.backup(out, "testpass")

    # Tamper with version
    data = json.loads(out.read_text())
    data["format_version"] = 999
    out.write_text(json.dumps(data))

    keystore.seed_path().unlink()
    keystore.salt_path().unlink()

    with pytest.raises(SystemExit):
        backup.restore(out, "testpass")


def test_backup_without_node_running(tmp_path, initialized_wallet):
    """Backup should work even when the LDK node is not running."""
    out = tmp_path / "backup.json"
    result = backup.backup(out, "testpass")
    assert result["has_peers"] is False
    assert result["has_channels"] is False
