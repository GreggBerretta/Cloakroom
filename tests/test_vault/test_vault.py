"""Tests for the vault manager."""

import os

import pytest

from cloakroom.exceptions import VaultCorruptedError
from cloakroom.models import VaultData, now_iso
from cloakroom.vault.crypto import generate_master_key
from cloakroom.vault.vault import Vault


@pytest.fixture
def master_key():
    return generate_master_key()


@pytest.fixture
def vault_path(tmp_path):
    return tmp_path / "test-vault.enc"


@pytest.fixture
def vault(vault_path):
    return Vault(vault_path)


@pytest.fixture
def sample_vault_data():
    return VaultData(
        workspace_id="test-ws-id",
        workspace_name="test-workspace",
        created_at=now_iso(),
        updated_at=now_iso(),
        ttl_hours=168,
    )


class TestVault:
    def test_save_and_load(self, vault, master_key, sample_vault_data):
        vault.save(sample_vault_data, master_key)
        assert vault.exists()

        loaded = vault.load(master_key)
        assert loaded.workspace_id == "test-ws-id"
        assert loaded.workspace_name == "test-workspace"

    def test_wrong_key_fails(self, vault, master_key, sample_vault_data):
        vault.save(sample_vault_data, master_key)

        wrong_key = generate_master_key()
        with pytest.raises(VaultCorruptedError):
            vault.load(wrong_key)

    def test_nonexistent_vault(self, vault, master_key):
        with pytest.raises(VaultCorruptedError, match="not found"):
            vault.load(master_key)

    def test_corrupted_file(self, vault, vault_path, master_key, sample_vault_data):
        vault.save(sample_vault_data, master_key)
        # Corrupt the file
        vault_path.write_bytes(b"corrupted data")
        with pytest.raises(VaultCorruptedError):
            vault.load(master_key)

    def test_destroy(self, vault, master_key, sample_vault_data):
        vault.save(sample_vault_data, master_key)
        assert vault.exists()
        vault.destroy()
        assert not vault.exists()

    def test_ttl_not_expired(self, vault, master_key, sample_vault_data):
        sample_vault_data.ttl_hours = 168
        vault.save(sample_vault_data, master_key)
        loaded = vault.load(master_key)
        assert loaded.workspace_name == "test-workspace"

    def test_mappings_persisted(self, vault, master_key, sample_vault_data):
        from cloakroom.models import EntityMapping, EntityType, Token

        token = Token(token_text="PERSON_001", entity_type=EntityType.PERSON, hmac_tag="abc")
        mapping = EntityMapping(
            token=token,
            original_value="John Smith",
            normalized_key="PERSON::john smith",
            entity_type=EntityType.PERSON,
            first_seen=now_iso(),
            source_files=["test.xlsx"],
        )
        sample_vault_data.mappings["PERSON::john smith"] = mapping
        sample_vault_data.token_counter["PERSON"] = 1

        vault.save(sample_vault_data, master_key)
        loaded = vault.load(master_key)

        assert "PERSON::john smith" in loaded.mappings
        assert loaded.mappings["PERSON::john smith"].original_value == "John Smith"
        assert loaded.token_counter["PERSON"] == 1

    def test_vault_file_permissions_enforced(self, vault, vault_path, master_key, sample_vault_data):
        vault.save(sample_vault_data, master_key)
        mode = os.stat(vault_path).st_mode & 0o777
        assert mode == 0o600
