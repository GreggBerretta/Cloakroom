"""Vault version migration from 1.0 to 2.0."""

from __future__ import annotations


CURRENT_VAULT_VERSION = "2.0"


def migrate_vault_data(data_dict: dict) -> dict:
    """Migrate vault data dict from any older version to current.

    Returns the migrated dict. Does not modify the input.
    Raises ValueError if the vault version is unrecognized.
    """
    version = data_dict.get("vault_version", "1.0")

    if version == CURRENT_VAULT_VERSION:
        return data_dict

    if version == "1.0":
        return _migrate_1_0_to_2_0(data_dict)

    raise ValueError(f"Unrecognized vault version: {version}")


def _migrate_1_0_to_2_0(data: dict) -> dict:
    """Add v2.0 fields with sensible defaults.

    The migration is additive: all v1.0 fields are preserved and new v2.0
    fields are injected with safe defaults so that existing workspaces
    continue to function without data loss.
    """
    migrated = dict(data)
    migrated["vault_version"] = "2.0"

    # Observability counters -- infer anonymize_count from existing file_records
    migrated.setdefault("anonymize_count", len(data.get("file_records", [])))
    migrated.setdefault("restore_count", 0)
    migrated.setdefault("abort_count", 0)
    migrated.setdefault("last_used", data.get("updated_at", ""))
    migrated.setdefault("shipped_client_work", False)
    migrated.setdefault("workspace_recall_type", "")

    # Behavioral prompt responses
    migrated.setdefault("trust_flip_responses", [])
    migrated.setdefault("rewrite_avoidance_responses", [])
    migrated.setdefault("pre_llm_capture_responses", [])

    # Attestation tracking
    migrated.setdefault("attestation_records", [])
    migrated.setdefault("attestation_completion_time", [])
    migrated.setdefault("attestation_abort_count", 0)

    # Timing data
    migrated.setdefault("time_to_close_after_restore", [])

    # Detection version lock
    migrated.setdefault("model_hashes", {})

    # Token format version
    migrated.setdefault("token_abi_version", "v1")
    migrated.setdefault("self_destruct_on_restore", False)
    return migrated
