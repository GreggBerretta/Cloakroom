"""Tests for deterministic replay and model-lock invariants."""

import pytest

from cloakroom.exceptions import ModelHashMismatchError, ReplayMismatchError
from cloakroom.models import DetectedEntity, EntityType, VaultData, now_iso
from cloakroom.pipeline.anonymize import AnonymizePipeline
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext


class FakeDetectionEngine:
    model_lock_key = "en_core_web_lg"

    def __init__(self, model_hash: str, detect_entities: bool = True):
        self._model_hash = model_hash
        self._detect_entities = detect_entities

    def get_model_hash(self) -> str:
        return self._model_hash

    def detect_in_cell(self, text: str, source_id: str):
        if not self._detect_entities:
            return []
        start = text.index("John Smith")
        return [
            DetectedEntity(
                entity_type=EntityType.PERSON,
                text="John Smith",
                start=start,
                end=start + len("John Smith"),
                score=0.99,
                source_id=source_id,
            )
        ]


@pytest.fixture
def workspace_ctx(tmp_path):
    master_key = generate_master_key()
    hmac_key = derive_hmac_key(master_key)
    vault_path = tmp_path / "vault.enc"
    vault = Vault(vault_path)
    vault_data = VaultData(
        workspace_id="test-id",
        workspace_name="test-ws",
        created_at=now_iso(),
        updated_at=now_iso(),
        ttl_hours=168,
    )
    token_gen = TokenGenerator(hmac_key)

    return WorkspaceContext(
        workspace_id="test-id",
        workspace_name="test-ws",
        vault=vault,
        vault_data=vault_data,
        token_generator=token_gen,
        master_key=master_key,
    )


class TestAnonymizeInvariants:
    def test_replay_mismatch_fails_without_override(self, workspace_ctx, tmp_path):
        input_path = tmp_path / "source.txt"
        input_path.write_text("John Smith", encoding="utf-8")

        first = AnonymizePipeline(workspace_ctx)
        first._detection = FakeDetectionEngine("hash-a", detect_entities=True)
        first.run(input_path, tmp_path / "first.anonymized.txt")

        second = AnonymizePipeline(workspace_ctx)
        second._detection = FakeDetectionEngine("hash-a", detect_entities=False)
        with pytest.raises(ReplayMismatchError):
            second.run(input_path, tmp_path / "second.anonymized.txt")

    def test_model_lock_mismatch_fails_without_override(self, workspace_ctx, tmp_path):
        input_path = tmp_path / "source.txt"
        input_path.write_text("John Smith", encoding="utf-8")

        first = AnonymizePipeline(workspace_ctx)
        first._detection = FakeDetectionEngine("hash-a", detect_entities=True)
        first.run(input_path, tmp_path / "first.anonymized.txt")

        second = AnonymizePipeline(workspace_ctx)
        second._detection = FakeDetectionEngine("hash-b", detect_entities=True)
        with pytest.raises(ModelHashMismatchError):
            second.run(input_path, tmp_path / "second.anonymized.txt")

    def test_override_is_audited(self, workspace_ctx, tmp_path):
        input_path = tmp_path / "source.txt"
        input_path.write_text("John Smith", encoding="utf-8")

        first = AnonymizePipeline(workspace_ctx)
        first._detection = FakeDetectionEngine("hash-a", detect_entities=True)
        first.run(input_path, tmp_path / "first.anonymized.txt")

        second = AnonymizePipeline(
            workspace_ctx,
            force_reanonymize=True,
            override_reason="model update approved",
            override_user="tester",
        )
        second._detection = FakeDetectionEngine("hash-b", detect_entities=True)
        second.run(input_path, tmp_path / "second.anonymized.txt")

        latest_record = workspace_ctx.vault_data.file_records[-1]
        assert latest_record.reanonymize_override is True
        assert latest_record.override_reason == "model update approved"
        assert latest_record.override_user == "tester"
        assert "manual_force_reanonymize" in latest_record.override_events
        assert "model_hash_mismatch" in latest_record.override_events
        assert workspace_ctx.vault_data.model_hashes["en_core_web_lg"] == "hash-b"
