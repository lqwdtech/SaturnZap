"""Tests for saturnzap.keystore — mnemonic generation and encrypted storage."""

from __future__ import annotations

import pytest

from saturnzap import keystore


@pytest.fixture()
def tmp_data_dir(tmp_path, monkeypatch):
    """Point saturnzap data dir to a temp directory."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


def test_generate_mnemonic_returns_24_words():
    m = keystore.generate_mnemonic()
    assert len(m.split()) == 24


def test_generate_mnemonic_is_unique():
    a = keystore.generate_mnemonic()
    b = keystore.generate_mnemonic()
    assert a != b


def test_encrypt_decrypt_round_trip(tmp_data_dir):
    mnemonic = keystore.generate_mnemonic()
    passphrase = "hunter2"
    keystore.save_encrypted(mnemonic, passphrase)
    recovered = keystore.load_mnemonic(passphrase)
    assert recovered == mnemonic


def test_wrong_passphrase_fails(tmp_data_dir):
    mnemonic = keystore.generate_mnemonic()
    keystore.save_encrypted(mnemonic, "correct-horse")
    with pytest.raises(SystemExit):
        keystore.load_mnemonic("wrong-battery")


def test_seed_file_permissions(tmp_data_dir):
    keystore.save_encrypted("abandon " * 23 + "art", "pw")
    sp = keystore.seed_path()
    mode = oct(sp.stat().st_mode & 0o777)
    assert mode == "0o600"


def test_is_initialized(tmp_data_dir):
    assert not keystore.is_initialized()
    keystore.save_encrypted("abandon " * 23 + "art", "pw")
    assert keystore.is_initialized()


def test_load_missing_seed_fails(tmp_data_dir):
    with pytest.raises(SystemExit):
        keystore.load_mnemonic("anything")


# ── Additional tests ─────────────────────────────────────────────


def test_corrupt_seed_file_fails(tmp_data_dir):
    """A corrupted seed.enc file should raise SystemExit (BAD_PASSPHRASE)."""
    d = tmp_data_dir / "saturnzap"
    d.mkdir(parents=True, exist_ok=True)
    (d / "seed.enc").write_bytes(b"corrupted-not-fernet-data")
    (d / "seed.salt").write_bytes(b"0" * 16)

    with pytest.raises(SystemExit):
        keystore.load_mnemonic("anything")


def test_missing_salt_file_fails(tmp_data_dir):
    """If seed.enc exists but seed.salt is missing, should fail."""
    d = tmp_data_dir / "saturnzap"
    d.mkdir(parents=True, exist_ok=True)
    (d / "seed.enc").write_bytes(b"fake")
    # No salt file

    with pytest.raises(SystemExit):
        keystore.load_mnemonic("anything")


def test_empty_passphrase_round_trip(tmp_data_dir):
    """Empty passphrase should still encrypt/decrypt correctly."""
    mnemonic = keystore.generate_mnemonic()
    keystore.save_encrypted(mnemonic, "")
    recovered = keystore.load_mnemonic("")
    assert recovered == mnemonic


def test_long_passphrase_round_trip(tmp_data_dir):
    """A very long passphrase should work."""
    mnemonic = keystore.generate_mnemonic()
    long_pp = "x" * 10_000
    keystore.save_encrypted(mnemonic, long_pp)
    recovered = keystore.load_mnemonic(long_pp)
    assert recovered == mnemonic


def test_salt_is_16_bytes(tmp_data_dir):
    """The saved salt should be exactly 16 bytes."""
    keystore.save_encrypted("abandon " * 23 + "art", "pw")
    salt = keystore.salt_path().read_bytes()
    assert len(salt) == 16


def test_different_encryptions_produce_different_salt(tmp_data_dir):
    """Two saves should produce different salts (random)."""
    keystore.save_encrypted("abandon " * 23 + "art", "pw")
    salt1 = keystore.salt_path().read_bytes()

    keystore.save_encrypted("abandon " * 23 + "art", "pw")
    salt2 = keystore.salt_path().read_bytes()

    assert salt1 != salt2


def test_get_passphrase_from_env(tmp_data_dir, monkeypatch):
    """get_passphrase should read from SZ_PASSPHRASE env var."""
    monkeypatch.setenv("SZ_PASSPHRASE", "envpass")
    assert keystore.get_passphrase() == "envpass"
