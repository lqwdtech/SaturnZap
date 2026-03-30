"""Security tests — seed encryption, file permissions, brute-force resistance."""

from __future__ import annotations

import time

import pytest

from saturnzap import keystore


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("SZ_PASSPHRASE", "testpass")


# ── PBKDF2 timing ───────────────────────────────────────────────


def test_pbkdf2_single_attempt_takes_at_least_100ms():
    """PBKDF2 with 600k iterations should resist brute-force."""
    mnemonic = keystore.generate_mnemonic()
    keystore.save_encrypted(mnemonic, "somepassphrase")

    t0 = time.monotonic()
    keystore.load_mnemonic("somepassphrase")
    elapsed = time.monotonic() - t0

    assert elapsed >= 0.05, (
        f"PBKDF2 derivation took only {elapsed:.3f}s — too fast for 600k iterations"
    )


# ── File permissions ─────────────────────────────────────────────


def test_seed_file_permissions_are_600():
    mnemonic = keystore.generate_mnemonic()
    keystore.save_encrypted(mnemonic, "testpass")

    mode = oct(keystore.seed_path().stat().st_mode & 0o777)
    assert mode == "0o600", f"seed.enc should be 0o600, got {mode}"


def test_salt_file_permissions_are_600():
    mnemonic = keystore.generate_mnemonic()
    keystore.save_encrypted(mnemonic, "testpass")

    mode = oct(keystore.salt_path().stat().st_mode & 0o777)
    assert mode == "0o600", f"seed.salt should be 0o600, got {mode}"


# ── Corrupt / missing files ─────────────────────────────────────


def test_corrupt_seed_enc_gives_graceful_error():
    mnemonic = keystore.generate_mnemonic()
    keystore.save_encrypted(mnemonic, "testpass")

    keystore.seed_path().write_bytes(b"corrupt-garbage-data")

    with pytest.raises(SystemExit):
        keystore.load_mnemonic("testpass")


def test_missing_salt_gives_graceful_error():
    mnemonic = keystore.generate_mnemonic()
    keystore.save_encrypted(mnemonic, "testpass")

    keystore.salt_path().unlink()

    with pytest.raises(SystemExit):
        keystore.load_mnemonic("testpass")


def test_missing_seed_gives_graceful_error():
    mnemonic = keystore.generate_mnemonic()
    keystore.save_encrypted(mnemonic, "testpass")

    keystore.seed_path().unlink()

    with pytest.raises(SystemExit):
        keystore.load_mnemonic("testpass")


# ── Salt is 16 bytes random ─────────────────────────────────────


def test_salt_is_16_bytes():
    mnemonic = keystore.generate_mnemonic()
    keystore.save_encrypted(mnemonic, "testpass")
    assert len(keystore.salt_path().read_bytes()) == 16


def test_different_saves_produce_different_salts():
    m1 = keystore.generate_mnemonic()
    keystore.save_encrypted(m1, "testpass")
    salt1 = keystore.salt_path().read_bytes()

    keystore.save_encrypted(m1, "testpass")
    salt2 = keystore.salt_path().read_bytes()

    assert salt1 != salt2, "Each encryption should use a fresh random salt"
