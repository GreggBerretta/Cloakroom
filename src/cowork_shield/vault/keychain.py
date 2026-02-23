"""macOS Keychain integration via the keyring library."""

from __future__ import annotations

import keyring
import subprocess

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


def verify_keychain_permissions() -> tuple[bool, str]:
    """Verify service entries are managed by macOS Keychain controls."""
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE_NAME],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False, "macOS security CLI not found."
    except Exception as e:
        raise KeychainError(f"Failed to verify Keychain permissions: {e}") from e

    if proc.returncode == 0:
        return True, "Keychain service entry found and gated by macOS security."

    stderr = (proc.stderr or "").strip().lower()
    if "could not be found" in stderr or "item could not be found" in stderr:
        return False, "No cowork-shield Keychain entry found."
    return False, f"Keychain check failed: {proc.stderr.strip() or proc.stdout.strip() or 'unknown error'}"
