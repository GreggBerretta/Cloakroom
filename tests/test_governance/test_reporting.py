"""Tests for governance sanitization reporting."""

from __future__ import annotations

import json
from pathlib import Path

from cloakroom.governance.reporting import (
    append_sanitization_report,
    build_anonymize_entity_counts,
    export_sanitization_reports,
    read_sanitization_reports,
    report_log_path_for_workspace_dir,
)
from cloakroom.models import EntityType, ReplacementRecord, VaultData, now_iso
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext


def _make_ctx(tmp_path: Path) -> WorkspaceContext:
    master_key = generate_master_key()
    hmac_key = derive_hmac_key(master_key)
    vault_path = tmp_path / "vault.enc"
    vault = Vault(vault_path)
    data = VaultData(
        workspace_id="ws-report",
        workspace_name="ws-report",
        created_at=now_iso(),
        updated_at=now_iso(),
        ttl_hours=24,
    )
    vault.save(data, master_key)
    generator = TokenGenerator(hmac_key)
    return WorkspaceContext(
        workspace_id="ws-report",
        workspace_name="ws-report",
        vault=vault,
        vault_data=data,
        token_generator=generator,
        master_key=master_key,
    )


def test_build_anonymize_entity_counts_supports_column_and_hebrew():
    records = [
        ReplacementRecord(
            location="r1",
            original_value="משה לוי",
            token_text="[PERSON_00001]",
            entity_type=EntityType.PERSON,
        ),
        ReplacementRecord(
            location="r2",
            original_value="Acme",
            token_text="[CLIENTNAME_00001]",
            entity_type=EntityType.COLUMN,
        ),
    ]
    counts = build_anonymize_entity_counts(records, language="he")
    assert counts["HE_PERSON"] == 1
    assert counts["COLUMN_CLIENTNAME"] == 1


def test_append_read_export_sanitization_reports(tmp_path):
    ctx = _make_ctx(tmp_path)
    append_sanitization_report(
        ctx,
        operation="anonymize",
        file_path="/tmp/sample.csv",
        file_ext=".csv",
        file_hash="a" * 64,
        duration_ms=1234,
        language="en",
        entity_counts={"PERSON": 2, "EMAIL": 1},
        entities_total=3,
        tokens_applied=3,
    )

    rows = read_sanitization_reports(ctx)
    assert len(rows) == 1
    assert rows[0]["operation"] == "anonymize"
    assert rows[0]["entities_total"] == 3
    assert rows[0]["file_hash"] == "a" * 64
    assert rows[0]["file_label_safe"] == "csv:aaaaaaaaaaaa"
    assert "file_path" not in rows[0]
    assert rows[0]["chain_verified"] is True

    export_path = tmp_path / "report.json"
    result_path = export_sanitization_reports(ctx, output_path=export_path, fmt="json")
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["workspace_id"] == ctx.workspace_id
    assert len(payload["reports"]) == 1


def test_report_storage_never_persists_raw_pii_filename(tmp_path):
    ctx = _make_ctx(tmp_path)
    toxic_path = tmp_path / "Jane Smith john.smith@acme.com 123-45-6789 Project Lantern.csv"

    append_sanitization_report(
        ctx,
        operation="anonymize",
        file_path=str(toxic_path),
        file_ext=".csv",
        file_hash="b" * 64,
        duration_ms=10,
        language="en",
        entity_counts={"PERSON": 1},
        entities_total=1,
        metadata={"file_path": str(toxic_path)},
    )

    report_path = report_log_path_for_workspace_dir(ctx.vault.path.parent)
    raw_report = report_path.read_text(encoding="utf-8")
    exported_path = export_sanitization_reports(
        ctx,
        output_path=tmp_path / "safe-report.json",
        fmt="json",
    )
    raw_export = exported_path.read_text(encoding="utf-8")

    for payload in (raw_report, raw_export):
        assert str(toxic_path) not in payload
        assert "Jane Smith" not in payload
        assert "john.smith@acme.com" not in payload
        assert "123-45-6789" not in payload
        assert "Project Lantern" not in payload

    rows = read_sanitization_reports(ctx)
    assert rows[0]["file_hash"] == "b" * 64
    assert rows[0]["file_label_safe"] == "csv:bbbbbbbbbbbb"
    assert "file_path" not in rows[0]
    assert "file_path" not in rows[0]["metadata"]
    assert "file_hash" in rows[0]["metadata"]
    assert "file_label_safe" in rows[0]["metadata"]


def test_report_hash_chain_detects_tampering(tmp_path):
    ctx = _make_ctx(tmp_path)

    first = append_sanitization_report(
        ctx,
        operation="anonymize",
        file_path="/tmp/first.csv",
        file_ext=".csv",
        file_hash="c" * 64,
        duration_ms=10,
        language="en",
        entity_counts={"PERSON": 1},
        entities_total=1,
    )
    second = append_sanitization_report(
        ctx,
        operation="restore",
        file_path="/tmp/second.csv",
        file_ext=".csv",
        file_hash="d" * 64,
        duration_ms=12,
        language="auto",
        entity_counts={"PERSON": 1},
        entities_total=1,
        tokens_restored=1,
    )

    assert first["report_hash"]
    assert second["prev_report_hash"] == first["report_hash"]
    assert second["chain_index"] == first["chain_index"] + 1
    assert [row["chain_verified"] for row in read_sanitization_reports(ctx)] == [True, True]

    report_path = report_log_path_for_workspace_dir(ctx.vault.path.parent)
    lines = report_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["entities_total"] = 99
    lines[0] = json.dumps(tampered, sort_keys=True, ensure_ascii=False)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tampered_rows = read_sanitization_reports(ctx)
    assert [row["chain_verified"] for row in tampered_rows] == [False, False]


def test_export_sanitization_reports_pdf_writes_valid_pdf(tmp_path):
    ctx = _make_ctx(tmp_path)
    append_sanitization_report(
        ctx,
        operation="anonymize",
        file_path="/tmp/customer_escalation.md",
        file_ext=".md",
        file_hash="e" * 64,
        duration_ms=42,
        language="en",
        entity_counts={"PERSON": 1, "EMAIL": 1},
        entities_total=2,
        tokens_applied=2,
    )
    out_path = tmp_path / "report.pdf"
    result_path = export_sanitization_reports(ctx, output_path=out_path, fmt="pdf")
    assert result_path == out_path.expanduser().resolve()
    payload = result_path.read_bytes()
    assert payload.startswith(b"%PDF-"), "Output is not a PDF"
    assert len(payload) > 200, "PDF looks suspiciously small"


def test_export_sanitization_reports_pdf_handles_empty_workspace(tmp_path):
    ctx = _make_ctx(tmp_path)
    out_path = tmp_path / "empty.pdf"
    export_sanitization_reports(ctx, output_path=out_path, fmt="pdf")
    payload = out_path.read_bytes()
    assert payload.startswith(b"%PDF-")
