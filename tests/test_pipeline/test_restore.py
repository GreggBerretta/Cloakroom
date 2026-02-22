"""Tests for the restoration pipeline with fail-closed verification."""

from pathlib import Path

import pytest

from cowork_shield.exceptions import IntegrityError, PdfInputOnlyError
from cowork_shield.models import EntityMapping, Token, VaultData, now_iso
from cowork_shield.pipeline.anonymize import AnonymizePipeline
from cowork_shield.pipeline.restore import RestorePipeline
from cowork_shield.tokenizer.generator import TokenGenerator
from cowork_shield.vault.crypto import derive_hmac_key, generate_master_key
from cowork_shield.vault.vault import Vault
from cowork_shield.workspace.manager import WorkspaceContext

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def master_key():
    return generate_master_key()


@pytest.fixture
def workspace_ctx(tmp_path, master_key):
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


class TestRestorePipeline:
    def test_csv_round_trip(self, workspace_ctx, tmp_path):
        # Anonymize
        anon_pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        anon_result = anon_pipeline.run(
            FIXTURES_DIR / "sample_data.csv",
            tmp_path / "anon.csv",
        )

        # Restore
        restore_pipeline = RestorePipeline(workspace_ctx)
        restore_result = restore_pipeline.run(
            anon_result.output_path,
            tmp_path / "restored.csv",
        )

        assert restore_result.verification_passed
        assert restore_result.tokens_restored > 0
        assert restore_result.output_path.exists()

    def test_xlsx_round_trip(self, workspace_ctx, tmp_path):
        anon_pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        anon_result = anon_pipeline.run(
            FIXTURES_DIR / "sample_contacts.xlsx",
            tmp_path / "anon.xlsx",
        )

        restore_pipeline = RestorePipeline(workspace_ctx)
        restore_result = restore_pipeline.run(
            anon_result.output_path,
            tmp_path / "restored.xlsx",
        )

        assert restore_result.verification_passed

    def test_docx_round_trip(self, workspace_ctx, tmp_path):
        anon_pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        anon_result = anon_pipeline.run(
            FIXTURES_DIR / "sample_report.docx",
            tmp_path / "anon.docx",
        )

        restore_pipeline = RestorePipeline(workspace_ctx)
        restore_result = restore_pipeline.run(
            anon_result.output_path,
            tmp_path / "restored.docx",
        )

        assert restore_result.verification_passed

    def test_markdown_round_trip(self, workspace_ctx, tmp_path):
        source_path = tmp_path / "notes.md"
        source_path.write_text(
            "# Draft\n\nJohn Smith can be reached at john@example.com.",
            encoding="utf-8",
        )

        anon_pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        anon_result = anon_pipeline.run(source_path, tmp_path / "notes.anonymized.md")

        restore_pipeline = RestorePipeline(workspace_ctx)
        restore_result = restore_pipeline.run(
            anon_result.output_path,
            tmp_path / "notes.restored.md",
        )

        assert restore_result.verification_passed
        assert restore_result.output_path.read_text(encoding="utf-8") == source_path.read_text(
            encoding="utf-8"
        )

    def test_fail_closed_corrupted_hmac(self, workspace_ctx, tmp_path):
        """Corrupted HMAC should abort restoration entirely."""
        # Anonymize first
        anon_pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        anon_result = anon_pipeline.run(
            FIXTURES_DIR / "sample_data.csv",
            tmp_path / "anon.csv",
        )

        # Corrupt an HMAC in the token generator's registry
        mappings = workspace_ctx.token_generator.get_all_mappings()
        if mappings:
            key = list(mappings.keys())[0]
            mapping = mappings[key]
            corrupted_token = Token(
                token_text=mapping.token.token_text,
                entity_type=mapping.token.entity_type,
                hmac_tag="corrupted_value",
            )
            corrupted_mapping = EntityMapping(
                token=corrupted_token,
                original_value=mapping.original_value,
                normalized_key=mapping.normalized_key,
                entity_type=mapping.entity_type,
                first_seen=mapping.first_seen,
                source_files=mapping.source_files,
            )
            # Replace in registry via load_state
            counters, all_mappings = workspace_ctx.token_generator.export_state()
            all_mappings[key] = corrupted_mapping
            workspace_ctx.token_generator.load_state(counters, all_mappings)

        restore_pipeline = RestorePipeline(workspace_ctx)
        with pytest.raises(IntegrityError, match="HMAC verification failed"):
            restore_pipeline.run(
                anon_result.output_path,
                tmp_path / "restored.csv",
            )

        # Output file should NOT exist (fail-closed)
        assert not (tmp_path / "restored.csv").exists()

    def test_no_mappings_error(self, tmp_path, master_key):
        """Empty workspace should fail to restore."""
        hmac_key = derive_hmac_key(master_key)
        vault = Vault(tmp_path / "vault.enc")
        vault_data = VaultData(
            workspace_id="empty-id",
            workspace_name="empty",
            created_at=now_iso(),
            updated_at=now_iso(),
            ttl_hours=168,
        )
        token_gen = TokenGenerator(hmac_key)
        ctx = WorkspaceContext(
            workspace_id="empty-id",
            workspace_name="empty",
            vault=vault,
            vault_data=vault_data,
            token_generator=token_gen,
            master_key=master_key,
        )

        # Create a dummy file to restore
        dummy = tmp_path / "dummy.csv"
        dummy.write_text("name\nPERSON_001\n")

        restore_pipeline = RestorePipeline(ctx)
        with pytest.raises(IntegrityError, match="No mappings"):
            restore_pipeline.run(dummy, tmp_path / "restored.csv")

    def test_default_output_strips_anonymized(self, workspace_ctx, tmp_path):
        """Output path should strip '.anonymized' from stem."""
        anon_pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        anon_result = anon_pipeline.run(
            FIXTURES_DIR / "sample_data.csv",
            tmp_path / "data.anonymized.csv",
        )

        restore_pipeline = RestorePipeline(workspace_ctx)
        result = restore_pipeline.run(anon_result.output_path)

        assert result.output_path.name == "data.restored.csv"

    def test_default_output_strips_anonymized_markdown(self, workspace_ctx, tmp_path):
        source_path = tmp_path / "brief.md"
        source_path.write_text("John Smith", encoding="utf-8")

        anon_pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        anon_result = anon_pipeline.run(source_path, tmp_path / "brief.anonymized.md")

        restore_pipeline = RestorePipeline(workspace_ctx)
        result = restore_pipeline.run(anon_result.output_path)

        assert result.output_path.name == "brief.restored.md"

    def test_restore_pdf_rejected_as_input_only(self, workspace_ctx, tmp_path):
        restore_pipeline = RestorePipeline(workspace_ctx)
        input_path = tmp_path / "payload.pdf"
        input_path.write_bytes(b"%PDF-1.4\\n")

        with pytest.raises(PdfInputOnlyError):
            restore_pipeline.run(input_path, tmp_path / "restored.pdf")
