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
