"""Tests for encrypted key recovery exports."""

from __future__ import annotations

import json

import pytest

from cowork_shield.exceptions import RecoveryKeyError
from cowork_shield.vault.crypto import generate_master_key
from cowork_shield.vault.recovery import (
    export_encrypted_master_key,
    import_encrypted_master_key,
)


class TestRecoveryExportImport:
    def test_round_trip(self):
        master_key = generate_master_key()
        blob = export_encrypted_master_key(
            workspace_id="ws-123",
            master_key=master_key,
            passphrase="correct horse battery staple",
        )
        workspace_id, decrypted = import_encrypted_master_key(
            blob=blob,
            passphrase="correct horse battery staple",
            expected_workspace_id="ws-123",
        )
        assert workspace_id == "ws-123"
        assert decrypted == master_key

    def test_wrong_passphrase_fails(self):
        master_key = generate_master_key()
        blob = export_encrypted_master_key(
            workspace_id="ws-123",
            master_key=master_key,
            passphrase="right-passphrase",
        )
        with pytest.raises(RecoveryKeyError, match="decrypt"):
            import_encrypted_master_key(
                blob=blob,
                passphrase="wrong-passphrase",
                expected_workspace_id="ws-123",
            )

    def test_workspace_mismatch_fails(self):
        master_key = generate_master_key()
        blob = export_encrypted_master_key(
            workspace_id="ws-a",
            master_key=master_key,
            passphrase="passphrase",
        )
        with pytest.raises(RecoveryKeyError, match="workspace"):
            import_encrypted_master_key(
                blob=blob,
                passphrase="passphrase",
                expected_workspace_id="ws-b",
            )

    def test_payload_is_json_and_versioned(self):
        master_key = generate_master_key()
        blob = export_encrypted_master_key(
            workspace_id="ws-123",
            master_key=master_key,
            passphrase="passphrase",
        )
        payload = json.loads(blob.decode("utf-8"))
        assert payload["version"] == 1
        assert payload["workspace_id"] == "ws-123"
        assert payload["kdf"]["name"] == "scrypt"
        assert payload["cipher"]["name"] == "aes-256-gcm"

    def test_export_payload_does_not_expose_master_key_material(self):
        master_key = generate_master_key()
        blob = export_encrypted_master_key(
            workspace_id="ws-456",
            master_key=master_key,
            passphrase="another-passphrase",
        )
        payload_text = blob.decode("utf-8")
        assert master_key.hex() not in payload_text
        payload = json.loads(payload_text)
        assert "ciphertext_b64" in payload["cipher"]
        assert payload["cipher"]["ciphertext_b64"]
