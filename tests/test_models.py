"""Tests for core data models."""

from cloakroom.models import (
    AttestationRecord,
    EntityMapping,
    EntityType,
    FileRecord,
    HallucinationFlag,
    Token,
    VaultData,
    now_iso,
)


class TestEntityType:
    def test_token_prefix(self):
        assert EntityType.PERSON.token_prefix == "PERSON"
        assert EntityType.ORGANIZATION.token_prefix == "ORG"
        assert EntityType.EMAIL.token_prefix == "EMAIL"

    def test_from_presidio(self):
        assert EntityType.from_presidio("PERSON") == EntityType.PERSON
        assert EntityType.from_presidio("EMAIL_ADDRESS") == EntityType.EMAIL
        assert EntityType.from_presidio("UNKNOWN_TYPE") is None

    def test_value_matches_presidio_string(self):
        assert EntityType.PERSON.value == "PERSON"
        assert EntityType.SSN.value == "US_SSN"
        assert EntityType.PHONE.value == "PHONE_NUMBER"


class TestToken:
    def test_frozen(self):
        token = Token(token_text="PERSON_001", entity_type=EntityType.PERSON, hmac_tag="abc")
        assert token.token_text == "PERSON_001"
        assert token.entity_type == EntityType.PERSON


class TestEntityMapping:
    def test_round_trip_serialization(self):
        token = Token(token_text="PERSON_001", entity_type=EntityType.PERSON, hmac_tag="abc123")
        mapping = EntityMapping(
            token=token,
            original_value="John Smith",
            normalized_key="PERSON::john smith",
            entity_type=EntityType.PERSON,
            first_seen="2026-02-21T10:00:00+00:00",
            source_files=["test.xlsx"],
        )

        d = mapping.to_dict()
        restored = EntityMapping.from_dict(d)

        assert restored.token.token_text == "PERSON_001"
        assert restored.original_value == "John Smith"
        assert restored.entity_type == EntityType.PERSON
        assert restored.source_files == ["test.xlsx"]


class TestVaultData:
    def test_round_trip_serialization(self):
        token = Token(token_text="ORG_001", entity_type=EntityType.ORGANIZATION, hmac_tag="xyz")
        mapping = EntityMapping(
            token=token,
            original_value="Acme Corp",
            normalized_key="ORGANIZATION::acme corp",
            entity_type=EntityType.ORGANIZATION,
            first_seen=now_iso(),
            source_files=["data.csv"],
        )

        vault_data = VaultData(
            workspace_id="test-id",
            workspace_name="test",
            created_at=now_iso(),
            updated_at=now_iso(),
            ttl_hours=168,
            mappings={"ORGANIZATION::acme corp": mapping},
            token_counter={"ORG": 1},
            file_records=[
                FileRecord(
                    file_path="/tmp/data.csv",
                    file_hash_before="abc",
                    file_hash_after="def",
                    anonymized_path="/tmp/data.anonymized.csv",
                    entities_found=5,
                    tokens_applied=3,
                    timestamp=now_iso(),
                    format="csv",
                )
            ],
        )

        d = vault_data.to_dict()
        restored = VaultData.from_dict(d)

        assert restored.workspace_id == "test-id"
        assert len(restored.mappings) == 1
        assert restored.token_counter["ORG"] == 1
        assert len(restored.file_records) == 1
        assert restored.file_records[0].format == "csv"

    def test_v2_fields_defaults(self):
        """New v2.0 fields should have safe defaults."""
        vault_data = VaultData(
            workspace_id="test-id",
            workspace_name="test",
            created_at=now_iso(),
            updated_at=now_iso(),
            ttl_hours=168,
        )
        assert vault_data.vault_version == "2.0"
        assert vault_data.anonymize_count == 0
        assert vault_data.restore_count == 0
        assert vault_data.abort_count == 0
        assert vault_data.last_used == ""
        assert vault_data.shipped_client_work is False
        assert vault_data.workspace_recall_type == ""
        assert vault_data.trust_flip_responses == []
        assert vault_data.rewrite_avoidance_responses == []
        assert vault_data.pre_llm_capture_responses == []
        assert vault_data.attestation_records == []
        assert vault_data.attestation_completion_time == []
        assert vault_data.attestation_abort_count == 0
        assert vault_data.time_to_close_after_restore == []
        assert vault_data.model_hashes == {}
        assert vault_data.token_abi_version == "v2"

    def test_v2_fields_round_trip(self):
        """V2 fields should survive serialization round-trip."""
        vault_data = VaultData(
            workspace_id="test-id",
            workspace_name="test",
            created_at=now_iso(),
            updated_at=now_iso(),
            ttl_hours=168,
            anonymize_count=5,
            restore_count=3,
            abort_count=1,
            last_used=now_iso(),
            shipped_client_work=True,
            workspace_recall_type="menu_bar",
            trust_flip_responses=[{"q": "test", "a": "yes"}],
            model_hashes={"en_core_web_lg": "abc123hash"},
            token_abi_version="v1",
        )
        d = vault_data.to_dict()
        restored = VaultData.from_dict(d)

        assert restored.anonymize_count == 5
        assert restored.restore_count == 3
        assert restored.abort_count == 1
        assert restored.shipped_client_work is True
        assert restored.workspace_recall_type == "menu_bar"
        assert len(restored.trust_flip_responses) == 1
        assert restored.model_hashes == {"en_core_web_lg": "abc123hash"}
        assert restored.token_abi_version == "v1"

    def test_v1_data_loads_with_defaults(self):
        """v1.0 vault data (missing v2 fields) should load with safe defaults."""
        v1_data = {
            "vault_version": "1.0",
            "workspace_id": "old-ws",
            "workspace_name": "legacy",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "ttl_hours": 48,
            "mappings": {},
            "token_counter": {},
            "file_records": [],
        }
        restored = VaultData.from_dict(v1_data)
        assert restored.vault_version == "1.0"
        assert restored.anonymize_count == 0
        assert restored.model_hashes == {}


class TestAttestationRecord:
    def test_round_trip_serialization(self):
        record = AttestationRecord(
            timestamp=now_iso(),
            user="cli",
            entity_count=15,
            entity_types={"PERSON": 5, "EMAIL_ADDRESS": 10},
            completion_time_seconds=12.5,
            confirmed=True,
            file_path="/tmp/data.xlsx",
        )
        d = record.to_dict()
        restored = AttestationRecord.from_dict(d)

        assert restored.user == "cli"
        assert restored.entity_count == 15
        assert restored.entity_types == {"PERSON": 5, "EMAIL_ADDRESS": 10}
        assert restored.completion_time_seconds == 12.5
        assert restored.confirmed is True
        assert restored.file_path == "/tmp/data.xlsx"


class TestHallucinationFlag:
    def test_round_trip_serialization(self):
        flag = HallucinationFlag(
            token_text="PERSON_99999",
            flag_type="hallucinated",
            nearest_match=None,
            position=42,
        )
        d = flag.to_dict()
        restored = HallucinationFlag.from_dict(d)

        assert restored.token_text == "PERSON_99999"
        assert restored.flag_type == "hallucinated"
        assert restored.nearest_match is None
        assert restored.position == 42

    def test_mutated_with_nearest_match(self):
        flag = HallucinationFlag(
            token_text="PERSON_00O01",
            flag_type="mutated",
            nearest_match="PERSON_00001",
            position=100,
        )
        d = flag.to_dict()
        restored = HallucinationFlag.from_dict(d)

        assert restored.flag_type == "mutated"
        assert restored.nearest_match == "PERSON_00001"

    def test_frozen(self):
        flag = HallucinationFlag("PERSON_00001", "hallucinated", None, 0)
        import pytest
        with pytest.raises(AttributeError):
            flag.token_text = "changed"
