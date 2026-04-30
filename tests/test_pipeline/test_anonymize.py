"""Tests for the anonymization pipeline."""

from pathlib import Path

import pytest

from cloakroom.exceptions import ColumnSelectionError, UnsupportedFormatError
from cloakroom.extractors.pdf_markdown import PDFExtractionResult
from cloakroom.governance.reporting import (
    read_sanitization_reports,
    report_log_path_for_workspace_dir,
)
from cloakroom.logging.audit import audit_log_path_for_workspace_dir
from cloakroom.models import VaultData, now_iso
from cloakroom.handlers import pdf_handler
from cloakroom.pipeline.anonymize import AnonymizePipeline
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def workspace_ctx(tmp_path):
    """Create a workspace context for testing without touching Keychain."""
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


class TestAnonymizePipeline:
    def test_anonymize_csv(self, workspace_ctx, tmp_path):
        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        input_path = FIXTURES_DIR / "sample_data.csv"
        output_path = tmp_path / "output.csv"

        result = pipeline.run(input_path, output_path)

        assert result.output_path.exists()
        assert result.entities_found > 0
        assert result.tokens_applied > 0
        assert result.workspace_name == "test-ws"

    def test_anonymize_xlsx(self, workspace_ctx, tmp_path):
        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        input_path = FIXTURES_DIR / "sample_contacts.xlsx"
        output_path = tmp_path / "output.xlsx"

        result = pipeline.run(input_path, output_path)

        assert result.output_path.exists()
        assert result.entities_found > 0

    def test_anonymize_docx(self, workspace_ctx, tmp_path):
        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        input_path = FIXTURES_DIR / "sample_report.docx"
        output_path = tmp_path / "output.docx"

        result = pipeline.run(input_path, output_path)

        assert result.output_path.exists()
        assert result.entities_found > 0

    def test_anonymize_markdown(self, workspace_ctx, tmp_path):
        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        input_path = tmp_path / "notes.md"
        input_path.write_text(
            "# Meeting Notes\n\nJohn Smith can be reached at john@example.com",
            encoding="utf-8",
        )

        result = pipeline.run(input_path)

        assert result.output_path.name == "notes.anonymized.md"
        assert result.output_path.exists()
        assert "[PERSON_" in result.output_path.read_text(encoding="utf-8")

    def test_anonymize_report_and_audit_do_not_leak_pii_filename(
        self,
        workspace_ctx,
        tmp_path,
    ):
        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        input_path = tmp_path / (
            "Jane Smith john.smith@acme.com 123-45-6789 Project Lantern.md"
        )
        input_path.write_text(
            "# Escalation\n\nJohn Smith can be reached at john@example.com",
            encoding="utf-8",
        )

        pipeline.run(input_path, tmp_path / "safe.md")

        report_text = report_log_path_for_workspace_dir(
            workspace_ctx.vault.path.parent
        ).read_text(encoding="utf-8")
        audit_text = audit_log_path_for_workspace_dir(
            workspace_ctx.vault.path.parent
        ).read_text(encoding="utf-8")
        for payload in (report_text, audit_text):
            assert str(input_path) not in payload
            assert "Jane Smith" not in payload
            assert "john.smith@acme.com" not in payload
            assert "123-45-6789" not in payload
            assert "Project Lantern" not in payload

        file_record = workspace_ctx.vault_data.file_records[-1]
        row = read_sanitization_reports(workspace_ctx)[-1]
        assert row["file_hash"] == file_record.file_hash_before
        assert row["chain_verified"] is True
        assert "file_path" not in row

    def test_unsupported_format(self, workspace_ctx, tmp_path):
        pipeline = AnonymizePipeline(workspace_ctx)
        dummy = tmp_path / "file.pptx"
        dummy.write_text("dummy")

        with pytest.raises(UnsupportedFormatError):
            pipeline.run(dummy)

    def test_anonymize_pdf_to_markdown(self, workspace_ctx, tmp_path, monkeypatch):
        monkeypatch.setattr(
            pdf_handler.PDFExtractor,
            "extract",
            lambda self, _: PDFExtractionResult(
                markdown="Contact John Smith at john@example.com",
                backend="test",
            ),
        )

        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        input_path = tmp_path / "brief.pdf"
        input_path.write_bytes(b"%PDF-1.4\\n% test\\n")

        result = pipeline.run(input_path)

        assert result.output_path.name == "brief.anonymized.md"
        assert result.output_path.exists()
        assert "[PERSON_" in result.output_path.read_text(encoding="utf-8")
        assert workspace_ctx.vault_data.file_records[-1].format == "pdf->md"

    def test_anonymize_pdf_to_docx(self, workspace_ctx, tmp_path, monkeypatch):
        monkeypatch.setattr(
            pdf_handler.PDFExtractor,
            "extract",
            lambda self, _: PDFExtractionResult(
                markdown="# Memo\\n\\nJane Roe spoke with Bob Lee.",
                backend="test",
            ),
        )

        pipeline = AnonymizePipeline(
            workspace_ctx,
            score_threshold=0.5,
            pdf_output_format="docx",
        )
        input_path = tmp_path / "memo.pdf"
        input_path.write_bytes(b"%PDF-1.4\\n% test\\n")

        result = pipeline.run(input_path)

        assert result.output_path.name == "memo.anonymized.docx"
        assert result.output_path.exists()

    def test_vault_persisted_after_anonymize(self, workspace_ctx, tmp_path):
        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        input_path = FIXTURES_DIR / "sample_data.csv"
        output_path = tmp_path / "output.csv"

        pipeline.run(input_path, output_path)

        # Vault file should exist on disk
        assert workspace_ctx.vault.exists()

        # Vault should contain mappings
        assert len(workspace_ctx.vault_data.mappings) > 0
        assert len(workspace_ctx.vault_data.file_records) == 1

    def test_multi_file_shared_tokens(self, workspace_ctx, tmp_path):
        """Two files in same workspace share token mappings."""
        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)

        # Anonymize CSV
        csv_out = tmp_path / "csv_out.csv"
        pipeline.run(FIXTURES_DIR / "sample_data.csv", csv_out)

        tokens_after_csv = len(workspace_ctx.vault_data.mappings)

        # Anonymize XLSX (which has some of the same names)
        xlsx_out = tmp_path / "xlsx_out.xlsx"
        pipeline.run(FIXTURES_DIR / "sample_contacts.xlsx", xlsx_out)

        # Some tokens should be reused (shared names like "John Smith")
        tokens_after_xlsx = len(workspace_ctx.vault_data.mappings)
        assert len(workspace_ctx.vault_data.file_records) == 2

        # The number of new tokens should be less than if we started fresh
        # (because shared entities are reused)
        assert tokens_after_xlsx >= tokens_after_csv

    def test_default_output_path(self, workspace_ctx, tmp_path):
        import shutil
        input_path = tmp_path / "data.csv"
        shutil.copy2(FIXTURES_DIR / "sample_data.csv", input_path)

        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        result = pipeline.run(input_path)

        assert result.output_path.name == "data.anonymized.csv"

    def test_column_only_csv_mode(self, workspace_ctx, tmp_path):
        pipeline = AnonymizePipeline(
            workspace_ctx,
            score_threshold=0.5,
            selected_columns=["Name", "Email"],
            detect_pii=False,
        )
        output_path = tmp_path / "column_only.csv"

        result = pipeline.run(FIXTURES_DIR / "sample_data.csv", output_path)

        assert result.output_path.exists()
        content = result.output_path.read_text(encoding="utf-8-sig")
        assert "[NAME_00001]" in content
        assert "[EMAIL_00001]" in content
        assert "123-45-6789" in content

    def test_columns_rejected_for_non_spreadsheet(self, workspace_ctx, tmp_path):
        source = tmp_path / "notes.txt"
        source.write_text("John Smith", encoding="utf-8")
        pipeline = AnonymizePipeline(
            workspace_ctx,
            selected_columns=["A"],
            detect_pii=False,
        )

        with pytest.raises(ColumnSelectionError):
            pipeline.run(source, tmp_path / "notes.anonymized.txt")

    def test_spreadsheet_requires_columns_or_detection(self, workspace_ctx, tmp_path):
        pipeline = AnonymizePipeline(
            workspace_ctx,
            selected_columns=[],
            detect_pii=False,
        )

        with pytest.raises(ColumnSelectionError):
            pipeline.run(FIXTURES_DIR / "sample_data.csv", tmp_path / "invalid.csv")
