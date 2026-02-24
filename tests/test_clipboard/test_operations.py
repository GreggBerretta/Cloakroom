"""Tests for clipboard shield/restore operations."""

from __future__ import annotations

import subprocess

import pytest

from cloakroom.clipboard import operations
from cloakroom.exceptions import HallucinationDetectedError
from cloakroom.models import DetectedEntity, EntityType, FileRecord, VaultData, now_iso
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext


class FakeDetectionEngine:
    model_lock_key = "en_core_web_lg"

    def __init__(self, score_threshold: float = 0.7):
        self._score_threshold = score_threshold

    def get_model_hash(self) -> str:
        return "model-a"

    def detect_in_cell(self, text: str, source_id: str):
        if "John Smith" not in text:
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


def _mock_clipboard(monkeypatch, initial_value: str):
    clipboard = {"value": initial_value}

    def fake_run(cmd, check, capture_output, text, input=None):  # noqa: A002
        if cmd[0] == "pbpaste":
            return subprocess.CompletedProcess(cmd, 0, stdout=clipboard["value"])
        if cmd[0] == "pbcopy":
            clipboard["value"] = input or ""
            return subprocess.CompletedProcess(cmd, 0, stdout="")
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr(operations.subprocess, "run", fake_run)
    return clipboard


class TestClipboardOperations:
    def test_shield_and_restore_roundtrip(self, workspace_ctx, monkeypatch):
        monkeypatch.setattr(operations, "DetectionEngine", FakeDetectionEngine)
        clipboard = _mock_clipboard(monkeypatch, "John Smith")

        shield_result = operations.shield_clipboard(workspace_ctx, score_threshold=0.5)
        assert shield_result.entities_found == 1
        assert shield_result.tokens_applied == 1
        assert clipboard["value"] == "[PERSON_00001]"

        restore_result = operations.restore_clipboard(workspace_ctx)
        assert restore_result.verification_passed is True
        assert clipboard["value"] == "John Smith"
        assert workspace_ctx.vault_data.anonymize_count == 1
        assert workspace_ctx.vault_data.restore_count == 1

    def test_restore_hallucination_aborts(self, workspace_ctx, monkeypatch):
        monkeypatch.setattr(operations, "DetectionEngine", FakeDetectionEngine)

        token = workspace_ctx.token_generator.get_or_create_token("John Smith", EntityType.PERSON)
        workspace_ctx.vault_data.file_records.append(
            FileRecord(
                file_path="<clipboard>",
                file_hash_before="before",
                file_hash_after="after",
                anonymized_path="<clipboard>",
                entities_found=1,
                tokens_applied=1,
                timestamp=now_iso(),
                format="clipboard",
                applied_tokens=[token.token_text],
            )
        )

        clipboard = _mock_clipboard(monkeypatch, "[PERSN_00001]")
        with pytest.raises(HallucinationDetectedError):
            operations.restore_clipboard(workspace_ctx)

        assert clipboard["value"] == "[PERSN_00001]"
