"""Tests for vault version migration."""

from __future__ import annotations

import pytest

from cowork_shield.vault.migration import (
    CURRENT_VAULT_VERSION,
    migrate_vault_data,
)


def _make_v1_vault_dict() -> dict:
    """Create a minimal valid v1.0 vault data dict."""
    return {
        "vault_version": "1.0",
        "workspace_id": "ws-123",
        "workspace_name": "test-workspace",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-02T00:00:00+00:00",
        "ttl_hours": 168,
        "token_counter": {"PERSON": 2, "ORG": 1},
        "mappings": {},
        "file_records": [
            {
                "file_path": "/tmp/a.csv",
                "file_hash_before": "abc",
                "file_hash_after": "def",
                "anonymized_path": "/tmp/a.anonymized.csv",
                "entities_found": 5,
                "tokens_applied": 3,
                "timestamp": "2026-01-01T01:00:00+00:00",
                "format": "csv",
            },
            {
                "file_path": "/tmp/b.xlsx",
                "file_hash_before": "ghi",
                "file_hash_after": "jkl",
                "anonymized_path": "/tmp/b.anonymized.xlsx",
                "entities_found": 10,
                "tokens_applied": 7,
                "timestamp": "2026-01-01T02:00:00+00:00",
                "format": "xlsx",
            },
        ],
    }


class TestMigrateVaultData:
    def test_v1_to_v2_bumps_version(self):
        data = _make_v1_vault_dict()
        migrated = migrate_vault_data(data)
        assert migrated["vault_version"] == "2.0"

    def test_v1_preserves_existing_fields(self):
        data = _make_v1_vault_dict()
        migrated = migrate_vault_data(data)
        assert migrated["workspace_id"] == "ws-123"
        assert migrated["workspace_name"] == "test-workspace"
        assert migrated["ttl_hours"] == 168
        assert migrated["token_counter"] == {"PERSON": 2, "ORG": 1}
        assert len(migrated["file_records"]) == 2

    def test_v1_infers_anonymize_count_from_file_records(self):
        data = _make_v1_vault_dict()
        migrated = migrate_vault_data(data)
        assert migrated["anonymize_count"] == 2  # 2 file_records

    def test_v1_sets_observability_defaults(self):
        data = _make_v1_vault_dict()
        migrated = migrate_vault_data(data)
        assert migrated["restore_count"] == 0
        assert migrated["abort_count"] == 0
        assert migrated["last_used"] == data["updated_at"]
        assert migrated["shipped_client_work"] is False
        assert migrated["workspace_recall_type"] == ""

    def test_v1_sets_behavioral_defaults(self):
        data = _make_v1_vault_dict()
        migrated = migrate_vault_data(data)
        assert migrated["trust_flip_responses"] == []
        assert migrated["rewrite_avoidance_responses"] == []
        assert migrated["pre_llm_capture_responses"] == []

    def test_v1_sets_attestation_defaults(self):
        data = _make_v1_vault_dict()
        migrated = migrate_vault_data(data)
        assert migrated["attestation_records"] == []
        assert migrated["attestation_completion_time"] == []
        assert migrated["attestation_abort_count"] == 0

    def test_v1_sets_timing_defaults(self):
        data = _make_v1_vault_dict()
        migrated = migrate_vault_data(data)
        assert migrated["time_to_close_after_restore"] == []

    def test_v1_sets_detection_lock_defaults(self):
        data = _make_v1_vault_dict()
        migrated = migrate_vault_data(data)
        assert migrated["model_hashes"] == {}
        assert migrated["token_abi_version"] == "v1"

    def test_v2_passes_through_unchanged(self):
        data = _make_v1_vault_dict()
        data["vault_version"] = "2.0"
        data["anonymize_count"] = 42
        result = migrate_vault_data(data)
        # Should be the same dict object (no migration needed)
        assert result is data
        assert result["anonymize_count"] == 42

    def test_does_not_mutate_input(self):
        data = _make_v1_vault_dict()
        original_version = data["vault_version"]
        migrate_vault_data(data)
        assert data["vault_version"] == original_version

    def test_unknown_version_raises(self):
        data = {"vault_version": "99.0"}
        with pytest.raises(ValueError, match="Unrecognized vault version"):
            migrate_vault_data(data)

    def test_missing_version_defaults_to_1_0(self):
        data = _make_v1_vault_dict()
        del data["vault_version"]
        migrated = migrate_vault_data(data)
        assert migrated["vault_version"] == "2.0"

    def test_current_vault_version_constant(self):
        assert CURRENT_VAULT_VERSION == "2.0"
