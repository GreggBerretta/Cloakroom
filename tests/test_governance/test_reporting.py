"""Tests for governance sanitization reporting."""

from __future__ import annotations

import json
from pathlib import Path

from cloakroom.governance.reporting import (
    append_sanitization_report,
    build_anonymize_entity_counts,
    export_sanitization_reports,
    read_sanitization_reports,
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

    export_path = tmp_path / "report.json"
    result_path = export_sanitization_reports(ctx, output_path=export_path, fmt="json")
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["workspace_id"] == ctx.workspace_id
    assert len(payload["reports"]) == 1
