"""BIP39 seed generation and encrypted storage.

The mnemonic is generated via ldk_node's built-in entropy, then
encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using a key
derived from the user-supplied passphrase.
"""

from __future__ import annotations

import base64
import getpass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from ldk_node import generate_entropy_mnemonic

from saturnzap.config import data_dir

SEED_FILENAME = "seed.enc"
SALT_FILENAME = "seed.salt"
PBKDF2_ITERATIONS = 600_000


def seed_path() -> Path:
    return data_dir() / SEED_FILENAME


def salt_path() -> Path:
    return data_dir() / SALT_FILENAME


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from passphrase + salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def generate_mnemonic() -> str:
    """Generate a new 24-word BIP39 mnemonic via LDK Node."""
    return generate_entropy_mnemonic(None)


def save_encrypted(mnemonic: str, passphrase: str) -> Path:
    """Encrypt *mnemonic* with *passphrase* and write to disk.

    Returns the path to the encrypted seed file.

    Enforces a minimum passphrase length (12 chars) to resist offline
    brute-force against the PBKDF2 key. Override with
    ``SZ_ALLOW_WEAK_PASSPHRASE=1`` for testing.
    """
    import os

    min_len = 12
    if len(passphrase) < min_len and os.environ.get(
        "SZ_ALLOW_WEAK_PASSPHRASE", ""
    ) != "1":
        from saturnzap import output
        output.error(
            "WEAK_PASSPHRASE",
            f"Passphrase must be at least {min_len} characters. "
            "Set SZ_ALLOW_WEAK_PASSPHRASE=1 to override (not recommended).",
        )

    salt = os.urandom(16)
    key = _derive_key(passphrase, salt)
    fernet = Fernet(key)
    encrypted = fernet.encrypt(mnemonic.encode("utf-8"))

    sp = seed_path()
    slp = salt_path()

    slp.write_bytes(salt)
    sp.write_bytes(encrypted)
    # Restrict permissions to owner-only
    sp.chmod(0o600)
    slp.chmod(0o600)
    return sp


def load_mnemonic(passphrase: str) -> str:
    """Decrypt and return the stored mnemonic.

    Raises ``SystemExit`` (via output.error) on wrong passphrase or missing file.
    """
    from saturnzap import output

    sp = seed_path()
    slp = salt_path()

    if not sp.exists() or not slp.exists():
        output.error("NO_SEED", "No seed found. Run 'sz init' first.", exit_code=1)

    salt = slp.read_bytes()
    key = _derive_key(passphrase, salt)
    fernet = Fernet(key)

    try:
        return fernet.decrypt(sp.read_bytes()).decode("utf-8")
    except InvalidToken:
        output.error("BAD_PASSPHRASE", "Incorrect passphrase.", exit_code=1)
    return ""  # unreachable, satisfies type checker


def get_passphrase(confirm: bool = False) -> str:
    """Return passphrase from ``SZ_PASSPHRASE`` env var, or prompt interactively."""
    import os

    pp = os.environ.get("SZ_PASSPHRASE")
    if pp:
        return pp
    return prompt_passphrase(confirm=confirm)


def prompt_passphrase(confirm: bool = False) -> str:
    """Prompt user for passphrase on stderr (never stdout)."""
    pp = getpass.getpass("Passphrase: ")
    if confirm:
        pp2 = getpass.getpass("Confirm passphrase: ")
        if pp != pp2:
            from saturnzap import output
            output.error(
                "PASSPHRASE_MISMATCH", "Passphrases do not match.", exit_code=1,
            )
    return pp


def is_initialized() -> bool:
    """Return True if an encrypted seed file already exists."""
    return seed_path().exists()
