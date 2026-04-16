"""Backup and restore — encrypted wallet export/import."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from saturnzap import keystore, output
from saturnzap.config import data_dir, load_config

FORMAT_VERSION = 1
PBKDF2_ITERATIONS = 600_000


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def backup(output_path: Path, passphrase: str) -> dict:
    """Create an encrypted backup of the wallet.

    Exports: mnemonic, peer list, channel info (reference only),
    L402 token cache, and config. Encrypted with PBKDF2+Fernet.

    Returns dict with backup metadata.
    """
    if not keystore.is_initialized():
        output.error("NO_SEED", "No wallet to backup. Run 'sz init' first.")

    mnemonic = keystore.load_mnemonic(passphrase)

    # Gather wallet data
    payload: dict = {
        "format_version": FORMAT_VERSION,
        "mnemonic": mnemonic,
        "config": load_config(),
    }

    # L402 token cache (optional, best-effort)
    token_dir = data_dir() / "l402_tokens"
    if token_dir.is_dir():
        tokens = {}
        for f in token_dir.iterdir():
            if f.is_file():
                tokens[f.name] = f.read_text().strip()
        payload["l402_tokens"] = tokens

    # Channel and peer info (reference only — not restorable)
    try:
        from saturnzap import node
        n = node.get_node()
        if n is not None:
            payload["peers"] = [
                {"node_id": p.node_id, "address": p.address}
                for p in n.list_peers()
            ]
            payload["channels"] = [
                {
                    "channel_id": str(c.channel_id),
                    "counterparty": c.counterparty_node_id,
                    "value_sats": c.channel_value_sats,
                }
                for c in n.list_channels()
            ]
    except Exception:  # noqa: BLE001, S110
        pass  # Node not running — skip peer/channel snapshot

    # Encrypt the payload
    plain = json.dumps(payload).encode("utf-8")
    salt = os.urandom(16)
    key = _derive_key(passphrase, salt)
    fernet = Fernet(key)
    encrypted = fernet.encrypt(plain)

    # Write backup file
    backup_data = {
        "saturnzap_backup": True,
        "format_version": FORMAT_VERSION,
        "salt": base64.b64encode(salt).decode("ascii"),
        "data": encrypted.decode("ascii"),
    }

    output_path = Path(output_path)
    output_path.write_text(json.dumps(backup_data, indent=2))
    output_path.chmod(0o600)

    return {
        "backup_path": str(output_path),
        "format_version": FORMAT_VERSION,
        "has_l402_tokens": "l402_tokens" in payload,
        "has_peers": "peers" in payload,
        "has_channels": "channels" in payload,
    }


def restore(input_path: Path, passphrase: str) -> dict:
    """Restore a wallet from an encrypted backup.

    Restores: mnemonic (as seed.enc), L402 token cache, config.
    Channels are NOT restorable (Lightning protocol limitation) — logged only.

    Returns dict with restore metadata.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        output.error("FILE_NOT_FOUND", f"Backup file not found: {input_path}")

    try:
        backup_data = json.loads(input_path.read_text())
    except (json.JSONDecodeError, ValueError):
        output.error("INVALID_BACKUP", "Backup file is not valid JSON.")

    if not backup_data.get("saturnzap_backup"):
        output.error("INVALID_BACKUP", "File is not a SaturnZap backup.")

    file_version = backup_data.get("format_version", 0)
    if file_version > FORMAT_VERSION:
        output.error(
            "VERSION_MISMATCH",
            f"Backup format v{file_version} is newer than supported v{FORMAT_VERSION}.",
        )

    # Decrypt
    try:
        salt = base64.b64decode(backup_data["salt"])
        key = _derive_key(passphrase, salt)
        fernet = Fernet(key)
        plain = fernet.decrypt(backup_data["data"].encode("ascii"))
        payload = json.loads(plain)
    except (InvalidToken, KeyError):
        output.error("BAD_PASSPHRASE", "Incorrect passphrase or corrupt backup.")

    # Validate decrypted payload schema. Fernet already authenticates
    # ciphertext (HMAC-SHA256), so corruption is caught above. These checks
    # defend against a malformed-but-valid-looking payload after decryption.
    if not isinstance(payload, dict):
        output.error("INVALID_BACKUP", "Backup payload is not a JSON object.")
    mnemonic = payload.get("mnemonic")
    if not isinstance(mnemonic, str):
        output.error("INVALID_BACKUP", "Backup missing mnemonic field.")
    word_count = len(mnemonic.split())
    if word_count not in (12, 15, 18, 21, 24):
        output.error(
            "INVALID_BACKUP",
            f"Backup mnemonic has {word_count} words; expected 12, 15, 18, 21, or 24.",
        )
    payload_version = payload.get("format_version")
    if not isinstance(payload_version, int) or payload_version > FORMAT_VERSION:
        output.error(
            "INVALID_BACKUP",
            "Backup payload has invalid format_version field.",
        )

    # Check if wallet already exists
    if keystore.is_initialized():
        output.error(
            "ALREADY_INITIALIZED",
            "Wallet already exists. Remove existing seed before restoring.",
        )

    # Restore mnemonic
    keystore.save_encrypted(mnemonic, passphrase)

    # Restore L402 token cache
    restored_tokens = 0
    l402_tokens = payload.get("l402_tokens", {})
    if l402_tokens:
        token_dir = data_dir() / "l402_tokens"
        token_dir.mkdir(parents=True, exist_ok=True)
        for name, token in l402_tokens.items():
            p = token_dir / name
            p.write_text(token)
            p.chmod(0o600)
            restored_tokens += 1

    # Log lost channels (informational only)
    lost_channels = payload.get("channels", [])

    return {
        "restored": True,
        "format_version": payload.get("format_version", FORMAT_VERSION),
        "restored_l402_tokens": restored_tokens,
        "lost_channels": lost_channels,
        "lost_channels_note": (
            "Lightning channels cannot be restored from backup. "
            "On-chain funds are recoverable from the seed."
            if lost_channels
            else None
        ),
    }
