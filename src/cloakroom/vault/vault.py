"""Encrypted JSON vault with atomic writes and TTL enforcement."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cloakroom.exceptions import VaultCorruptedError, WorkspaceExpiredError
from cloakroom.models import VaultData, now_iso
from cloakroom.vault.atomic import atomic_write
from cloakroom.vault.crypto import decrypt, derive_vault_key, encrypt
from cloakroom.vault.migration import migrate_vault_data


class Vault:
    """Manages encrypted vault files on disk.

    Each workspace has one vault file containing all entity mappings,
    token counters, and file records. The vault is encrypted with a key
    derived from the workspace's master key (stored in Keychain).
    """

    def __init__(self, vault_path: Path):
        self._path = vault_path

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def save(self, data: VaultData, master_key: bytes) -> None:
        """Encrypt and atomically write vault data to disk."""
        data.updated_at = now_iso()
        vault_key = derive_vault_key(master_key)
        plaintext = json.dumps(data.to_dict(), ensure_ascii=False).encode("utf-8")
        encrypted = encrypt(plaintext, vault_key)
        atomic_write(self._path, encrypted)
        os.chmod(self._path, 0o600)

    def load(self, master_key: bytes) -> VaultData:
        """Load and decrypt vault, checking TTL."""
        if not self._path.exists():
            raise VaultCorruptedError(f"Vault file not found: {self._path}")

        vault_key = derive_vault_key(master_key)
        raw = self._path.read_bytes()

        try:
            plaintext = decrypt(raw, vault_key)
        except Exception as e:
            raise VaultCorruptedError(
                f"Failed to decrypt vault (wrong key or corrupted data): {e}"
            ) from e

        try:
            data_dict = json.loads(plaintext.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise VaultCorruptedError(f"Vault JSON is corrupted: {e}") from e

        # Migrate vault data from older versions if needed
        data_dict = migrate_vault_data(data_dict)

        vault_data = VaultData.from_dict(data_dict)

        if self._is_expired(vault_data):
            raise WorkspaceExpiredError(vault_data.workspace_name)

        return vault_data

    def destroy(self) -> None:
        """Delete the vault file from disk."""
        if self._path.exists():
            self._path.unlink()

    @staticmethod
    def _is_expired(data: VaultData) -> bool:
        """Check if the vault's TTL has elapsed."""
        if data.ttl_hours <= 0:
            return False
        created = datetime.fromisoformat(data.created_at)
        now = datetime.now(timezone.utc)
        elapsed_hours = (now - created).total_seconds() / 3600
        return elapsed_hours > data.ttl_hours
