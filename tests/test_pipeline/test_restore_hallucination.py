"""Tests for hallucination fail-closed behavior in restore pipeline."""

import pytest

from cloakroom.exceptions import HallucinationDetectedError
from cloakroom.models import EntityType, FileRecord, VaultData, now_iso
from cloakroom.pipeline.restore import RestorePipeline
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext


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
    token = token_gen.get_or_create_token("John Smith", EntityType.PERSON)

    # Track expected token list for dropped-token detection.
    vault_data.file_records.append(
        FileRecord(
            file_path=str(tmp_path / "source.txt"),
            file_hash_before="before",
            file_hash_after="after",
            anonymized_path=str(tmp_path / "ai_output.txt"),
            entities_found=1,
            tokens_applied=1,
            timestamp=now_iso(),
            format="txt",
            applied_tokens=[token.token_text],
        )
    )

    return WorkspaceContext(
        workspace_id="test-id",
        workspace_name="test-ws",
        vault=vault,
        vault_data=vault_data,
        token_generator=token_gen,
        master_key=master_key,
    )


class TestRestoreHallucination:
    def test_mutated_token_aborts_restore(self, workspace_ctx, tmp_path):
        input_path = tmp_path / "ai_output.txt"
        input_path.write_text("[PERSN_00001]", encoding="utf-8")

        pipeline = RestorePipeline(workspace_ctx)
        with pytest.raises(HallucinationDetectedError) as exc:
            pipeline.run(input_path, tmp_path / "restored.txt")

        assert any(flag.flag_type == "mutated" for flag in exc.value.flags)
        assert not (tmp_path / "restored.txt").exists()

    def test_dropped_token_aborts_restore(self, workspace_ctx, tmp_path):
        input_path = tmp_path / "ai_output.txt"
        input_path.write_text("token removed by model", encoding="utf-8")

        pipeline = RestorePipeline(workspace_ctx)
        with pytest.raises(HallucinationDetectedError) as exc:
            pipeline.run(input_path, tmp_path / "restored.txt")

        assert any(flag.flag_type == "dropped" for flag in exc.value.flags)
        assert not (tmp_path / "restored.txt").exists()
