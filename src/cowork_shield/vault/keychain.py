"""macOS Keychain integration via the keyring library."""

from __future__ import annotations

import keyring

from cowork_shield.exceptions import KeychainError

SERVICE_NAME = "cowork-shield"


def store_master_key(workspace_id: str, key: bytes) -> None:
    """Store a workspace's master key in the macOS Keychain."""
    try:
        keyring.set_password(SERVICE_NAME, workspace_id, key.hex())
    except Exception as e:
        raise KeychainError(f"Failed to store key in Keychain: {e}") from e


def get_master_key(workspace_id: str) -> bytes | None:
    """Retrieve a workspace's master key from Keychain.

    Returns None if no key exists for this workspace.
    """
    try:
        hex_key = keyring.get_password(SERVICE_NAME, workspace_id)
        if hex_key is None:
            return None
        return bytes.fromhex(hex_key)
    except Exception as e:
        raise KeychainError(f"Failed to retrieve key from Keychain: {e}") from e


def delete_master_key(workspace_id: str) -> None:
    """Remove a workspace's master key from Keychain."""
    try:
        keyring.delete_password(SERVICE_NAME, workspace_id)
    except keyring.errors.PasswordDeleteError:
        pass  # Already deleted
    except Exception as e:
        raise KeychainError(f"Failed to delete key from Keychain: {e}") from e
