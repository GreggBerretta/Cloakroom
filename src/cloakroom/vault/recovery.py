"""Encrypted master-key export/import helpers for disaster recovery."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from cloakroom.exceptions import RecoveryKeyError

RECOVERY_EXPORT_VERSION = 1
_SALT_SIZE = 16
_NONCE_SIZE = 12
_DERIVED_KEY_SIZE = 32


def export_encrypted_master_key(
    *,
    workspace_id: str,
    master_key: bytes,
    passphrase: str,
) -> bytes:
    """Encrypt a workspace master key for recovery transfer."""
    if not workspace_id:
        raise RecoveryKeyError("Workspace ID is required for key export.")
    if len(master_key) != _DERIVED_KEY_SIZE:
        raise RecoveryKeyError("Master key length is invalid.")
    if not passphrase:
        raise RecoveryKeyError("Passphrase must not be empty.")

    salt = os.urandom(_SALT_SIZE)
    nonce = os.urandom(_NONCE_SIZE)
    derived = _derive_passphrase_key(passphrase, salt)
    ciphertext = AESGCM(derived).encrypt(nonce, master_key, None)

    payload = {
        "version": RECOVERY_EXPORT_VERSION,
        "workspace_id": workspace_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kdf": {
            "name": "scrypt",
            "n": 2 ** 14,
            "r": 8,
            "p": 1,
            "salt_b64": _to_b64(salt),
        },
        "cipher": {
            "name": "aes-256-gcm",
            "nonce_b64": _to_b64(nonce),
            "ciphertext_b64": _to_b64(ciphertext),
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def import_encrypted_master_key(
    *,
    blob: bytes,
    passphrase: str,
    expected_workspace_id: str | None = None,
) -> tuple[str, bytes]:
    """Decrypt an exported recovery key payload.

    Returns `(workspace_id, master_key)`.
    """
    if not passphrase:
        raise RecoveryKeyError("Passphrase must not be empty.")

    try:
        data = json.loads(blob.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise RecoveryKeyError(f"Recovery payload is not valid JSON: {exc}") from exc

    try:
        version = int(data["version"])
        workspace_id = str(data["workspace_id"])
        salt = _from_b64(data["kdf"]["salt_b64"])
        nonce = _from_b64(data["cipher"]["nonce_b64"])
        ciphertext = _from_b64(data["cipher"]["ciphertext_b64"])
    except Exception as exc:  # noqa: BLE001
        raise RecoveryKeyError(f"Recovery payload schema is invalid: {exc}") from exc

    if version != RECOVERY_EXPORT_VERSION:
        raise RecoveryKeyError(
            f"Unsupported recovery payload version: {version}"
        )
    if expected_workspace_id and workspace_id != expected_workspace_id:
        raise RecoveryKeyError(
            f"Recovery key is for workspace '{workspace_id}', not '{expected_workspace_id}'."
        )

    derived = _derive_passphrase_key(passphrase, salt)
    try:
        master_key = AESGCM(derived).decrypt(nonce, ciphertext, None)
    except Exception as exc:  # noqa: BLE001
        raise RecoveryKeyError("Failed to decrypt recovery key payload.") from exc

    if len(master_key) != _DERIVED_KEY_SIZE:
        raise RecoveryKeyError("Decrypted master key has invalid length.")
    return workspace_id, master_key


def _derive_passphrase_key(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(
        salt=salt,
        length=_DERIVED_KEY_SIZE,
        n=2 ** 14,
        r=8,
        p=1,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def _to_b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _from_b64(encoded: str) -> bytes:
    return base64.b64decode(encoded.encode("ascii"))

