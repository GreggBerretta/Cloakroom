"""Hallucination detection tests for PDF-derived markdown with Hebrew content."""

from __future__ import annotations

import pytest

from cowork_shield.exceptions import HallucinationDetectedError
from cowork_shield.models import EntityType, FileRecord, VaultData, now_iso
from cowork_shield.pipeline.restore import RestorePipeline
from cowork_shield.tokenizer.generator import TokenGenerator
from cowork_shield.vault.crypto import derive_hmac_key, generate_master_key
from cowork_shield.vault.vault import Vault
from cowork_shield.workspace.manager import WorkspaceContext


@pytest.fixture
def pdf_hebrew_ctx(tmp_path):
    master_key = generate_master_key()
    hmac_key = derive_hmac_key(master_key)
    vault_path = tmp_path / "vault.enc"
    vault = Vault(vault_path)
    vault_data = VaultData(
        workspace_id="pdf-he-id",
        workspace_name="pdf-he-ws",
        created_at=now_iso(),
        updated_at=now_iso(),
        ttl_hours=168,
    )
    token_gen = TokenGenerator(hmac_key)

    hebrew_name = "משה כהן"
    token = token_gen.get_or_create_token(hebrew_name, EntityType.PERSON)

    input_path = tmp_path / "client_report.anonymized.md"
    vault_data.file_records.append(
        FileRecord(
            file_path=str(tmp_path / "client_report.pdf"),
            file_hash_before="pdf-before",
            file_hash_after="md-after",
            anonymized_path=str(input_path),
            entities_found=1,
            tokens_applied=1,
            timestamp=now_iso(),
            format="pdf->md",
            applied_tokens=[token.token_text],
        )
    )

    ctx = WorkspaceContext(
        workspace_id="pdf-he-id",
        workspace_name="pdf-he-ws",
        vault=vault,
        vault_data=vault_data,
        token_generator=token_gen,
        master_key=master_key,
    )

    return {
        "ctx": ctx,
        "input_path": input_path,
        "token": token.token_text,
        "hebrew_name": hebrew_name,
    }


def test_valid_restore_no_flags_pdf_hebrew(pdf_hebrew_ctx, tmp_path):
    input_path = pdf_hebrew_ctx["input_path"]
    token = pdf_hebrew_ctx["token"]
    output_path = tmp_path / "client_report.restored.md"

    input_path.write_text(f"סיכום לקוח: {token}", encoding="utf-8")

    result = RestorePipeline(pdf_hebrew_ctx["ctx"]).run(input_path, output_path)

    assert result.verification_passed is True
    restored = output_path.read_text(encoding="utf-8")
    assert pdf_hebrew_ctx["hebrew_name"] in restored
    assert token not in restored


def test_mutated_token_detected_pdf_hebrew(pdf_hebrew_ctx, tmp_path):
    input_path = pdf_hebrew_ctx["input_path"]
    output_path = tmp_path / "client_report.restored.md"
    input_path.write_text("סיכום לקוח: [PERSN_00001]", encoding="utf-8")

    with pytest.raises(HallucinationDetectedError) as exc:
        RestorePipeline(pdf_hebrew_ctx["ctx"]).run(input_path, output_path)

    assert any(flag.flag_type == "mutated" for flag in exc.value.flags)
    assert not output_path.exists()


def test_hallucinated_token_detected_pdf_hebrew(pdf_hebrew_ctx, tmp_path):
    input_path = pdf_hebrew_ctx["input_path"]
    output_path = tmp_path / "client_report.restored.md"
    input_path.write_text("סיכום לקוח: [PERSON_99999]", encoding="utf-8")

    with pytest.raises(HallucinationDetectedError) as exc:
        RestorePipeline(pdf_hebrew_ctx["ctx"]).run(input_path, output_path)

    assert any(flag.flag_type == "hallucinated" for flag in exc.value.flags)
    assert not output_path.exists()


def test_dropped_token_detected_pdf_hebrew(pdf_hebrew_ctx, tmp_path):
    input_path = pdf_hebrew_ctx["input_path"]
    output_path = tmp_path / "client_report.restored.md"
    input_path.write_text("סיכום לקוח ללא טוקנים", encoding="utf-8")

    with pytest.raises(HallucinationDetectedError) as exc:
        RestorePipeline(pdf_hebrew_ctx["ctx"]).run(input_path, output_path)

    assert any(flag.flag_type == "dropped" for flag in exc.value.flags)
    assert not output_path.exists()


@pytest.mark.parametrize(
    ("payload", "expected_flag"),
    [
        ("[PERSN_00001]", "mutated"),
        ("[PERSON_99999]", "hallucinated"),
        ("אין טוקן בכלל", "dropped"),
    ],
)
def test_restore_aborts_on_detection_pdf_hebrew(pdf_hebrew_ctx, tmp_path, payload, expected_flag):
    input_path = pdf_hebrew_ctx["input_path"]
    output_path = tmp_path / "client_report.restored.md"
    input_path.write_text(f"סיכום: {payload}", encoding="utf-8")

    with pytest.raises(HallucinationDetectedError) as exc:
        RestorePipeline(pdf_hebrew_ctx["ctx"]).run(input_path, output_path)

    assert any(flag.flag_type == expected_flag for flag in exc.value.flags)
    assert not output_path.exists()
