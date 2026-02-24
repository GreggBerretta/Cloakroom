"""Vault governance sanitization reports (auditor-safe, local-only)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any

from cloakroom.logging.sanitizer import sanitize_value
from cloakroom.models import EntityType, ReplacementRecord

if TYPE_CHECKING:
    from cloakroom.workspace.manager import WorkspaceContext


REPORT_FILENAME = "sanitization_report.jsonl"
_HEBREW_SCRIPT_RE = re.compile(r"[\u0590-\u05FF]")


def append_sanitization_report(
    ctx: "WorkspaceContext",
    *,
    operation: str,
    file_path: str,
    file_ext: str,
    duration_ms: int,
    language: str,
    entity_counts: dict[str, int],
    entities_total: int,
    tokens_applied: int = 0,
    tokens_restored: int = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one sanitizer-safe report row for governance/auditor workflows."""
    safe_metadata, _ = sanitize_value(metadata or {})
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace_id": ctx.workspace_id,
        "workspace_name": ctx.workspace_name,
        "operation": operation,
        "file_path": file_path,
        "file_ext": file_ext,
        "duration_ms": int(duration_ms),
        "language": language,
        "entities_total": int(entities_total),
        "entity_counts": dict(sorted(entity_counts.items())),
        "tokens_applied": int(tokens_applied),
        "tokens_restored": int(tokens_restored),
        "metadata": safe_metadata,
    }
    path = report_log_path_for_workspace_dir(ctx.vault.path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", opener=_secure_opener) as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        handle.write("\n")
    return payload


def read_sanitization_reports(
    ctx: "WorkspaceContext",
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Read previously stored sanitizer-safe operation reports."""
    path = report_log_path_for_workspace_dir(ctx.vault.path.parent)
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            safe, _ = sanitize_value(parsed)
            rows.append(safe)
        except Exception:
            continue

    if limit is not None and limit > 0:
        return rows[-limit:]
    return rows


def export_sanitization_reports(
    ctx: "WorkspaceContext",
    *,
    output_path: Path,
    fmt: str = "json",
) -> Path:
    """Export reports as JSON (or basic PDF text rendering)."""
    fmt = (fmt or "json").strip().lower()
    rows = read_sanitization_reports(ctx)

    resolved = output_path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        payload = {
            "workspace_id": ctx.workspace_id,
            "workspace_name": ctx.workspace_name,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "reports": rows,
        }
        resolved.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.chmod(resolved, 0o600)
        return resolved

    if fmt == "pdf":
        _export_reports_pdf(rows, resolved, workspace_name=ctx.workspace_name)
        os.chmod(resolved, 0o600)
        return resolved

    raise ValueError(f"Unsupported export format: {fmt}")


def report_log_path_for_workspace_dir(workspace_dir: Path) -> Path:
    return workspace_dir / REPORT_FILENAME


def build_anonymize_entity_counts(
    records: list[ReplacementRecord],
    *,
    language: str,
) -> dict[str, int]:
    """Aggregate replacement records into governance-safe typed counts."""
    counts: Counter[str] = Counter()
    normalized_language = (language or "").strip().lower()
    for record in records:
        key = _count_key_for_record(record, language=normalized_language)
        counts[key] += 1
    return dict(counts)


def build_restore_entity_counts(
    *,
    token_texts: set[str],
    token_to_entity_type: dict[str, EntityType],
    token_to_original: dict[str, str] | None = None,
) -> dict[str, int]:
    """Aggregate restore token set into type counts."""
    counts: Counter[str] = Counter()
    originals = token_to_original or {}
    for token in token_texts:
        entity_type = token_to_entity_type.get(token)
        if entity_type is None:
            continue
        if entity_type is EntityType.COLUMN:
            prefix = _extract_column_prefix_from_token(token) or "UNKNOWN"
            counts[f"COLUMN_{prefix}"] += 1
            continue

        original = originals.get(token, "")
        if original and _HEBREW_SCRIPT_RE.search(original):
            counts[f"HE_{entity_type.token_prefix}"] += 1
        else:
            counts[entity_type.token_prefix] += 1
    return dict(counts)


def _count_key_for_record(record: ReplacementRecord, *, language: str) -> str:
    if record.entity_type is EntityType.COLUMN:
        prefix = _extract_column_prefix_from_token(record.token_text) or "UNKNOWN"
        return f"COLUMN_{prefix}"

    is_hebrew = language == "he" or bool(_HEBREW_SCRIPT_RE.search(record.original_value))
    if is_hebrew:
        return f"HE_{record.entity_type.token_prefix}"
    return record.entity_type.token_prefix


def _extract_column_prefix_from_token(token_text: str) -> str:
    token = token_text.strip()
    if token.startswith("[") and token.endswith("]"):
        token = token[1:-1]
    if "_" not in token:
        return ""
    prefix = token.split("_", 1)[0].strip().upper()
    return re.sub(r"[^A-Z0-9]+", "", prefix)[:32]


def _export_reports_pdf(rows: list[dict[str, Any]], path: Path, *, workspace_name: str) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 48.0
    page.insert_text((48, y), f"Cloakroom Sanitization Report: {workspace_name}", fontsize=12)
    y += 20.0

    if not rows:
        page.insert_text((48, y), "No report entries found.", fontsize=10)
        doc.save(str(path))
        doc.close()
        return

    for row in rows:
        line = (
            f"{row.get('timestamp', '')} | {row.get('operation', '')} | "
            f"entities={row.get('entities_total', 0)} | "
            f"tokens_applied={row.get('tokens_applied', 0)} | "
            f"tokens_restored={row.get('tokens_restored', 0)}"
        )
        if y > 770:
            page = doc.new_page()
            y = 48.0
        page.insert_text((48, y), line[:180], fontsize=9)
        y += 14.0

    doc.save(str(path))
    doc.close()


def _secure_opener(path: str, flags: int) -> int:
    return os.open(path, flags, 0o600)
