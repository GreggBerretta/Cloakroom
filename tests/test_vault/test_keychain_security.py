"""Tests for keychain security checks and fail-closed behavior."""

from __future__ import annotations

from subprocess import CompletedProcess

import pytest

from cloakroom.exceptions import KeychainError
from cloakroom.vault import keychain


def test_verify_keychain_permissions_pass(monkeypatch):
    monkeypatch.setattr(
        keychain.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args=args[0], returncode=0, stdout="", stderr=""),
    )
    ok, detail = keychain.verify_keychain_permissions()
    assert ok is True
    assert "Keychain service entry found" in detail


def test_verify_keychain_permissions_missing_entry(monkeypatch):
    monkeypatch.setattr(
        keychain.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=44,
            stdout="",
            stderr="security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.",
        ),
    )
    ok, detail = keychain.verify_keychain_permissions()
    assert ok is False
    assert "No cloakroom Keychain entry found" in detail


def test_verify_keychain_permissions_handles_missing_security_cli(monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("security not found")

    monkeypatch.setattr(keychain.subprocess, "run", _raise)
    ok, detail = keychain.verify_keychain_permissions()
    assert ok is False
    assert "security CLI not found" in detail


def test_store_master_key_fail_closed(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("keyring unavailable")

    monkeypatch.setattr(keychain.keyring, "set_password", _raise)
    with pytest.raises(KeychainError, match="Failed to store key in Keychain"):
        keychain.store_master_key("ws-1", b"\x00" * 32)

