"""Workspace audit trail with HMAC tamper evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cloakroom.governance.file_identity import scrub_file_references
from cloakroom.logging.sanitizer import sanitize_value
from cloakroom.vault.crypto import derive_hmac_key

if TYPE_CHECKING:
    from cloakroom.workspace.manager import WorkspaceContext

AUDIT_FILENAME = "audit.log.jsonl"


@dataclass(frozen=True)
class AuditEventRecord:
    record: dict[str, Any]
    signature: str
    verified: bool


def append_audit_event(
    ctx: "WorkspaceContext",
    *,
    event: str,
    fields: dict[str, Any],
) -> None:
    """Append a signed audit event for a workspace."""
    safe_fields, _ = sanitize_value(scrub_file_references(fields))
    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace_id": ctx.workspace_id,
        "workspace_name": ctx.workspace_name,
        "fields": safe_fields,
    }
    signature = _sign_payload(payload, ctx.master_key)
    entry = {"record": payload, "signature": signature}
    path = _audit_path_for_context(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", opener=_secure_opener) as handle:
        handle.write(json.dumps(entry, ensure_ascii=False))
        handle.write("\n")


def read_audit_events(ctx: "WorkspaceContext") -> list[AuditEventRecord]:
    path = _audit_path_for_context(ctx)
    if not path.exists():
        return []
    rows: list[AuditEventRecord] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            record = row["record"]
            signature = row["signature"]
            expected = _sign_payload(record, ctx.master_key)
            rows.append(
                AuditEventRecord(
                    record=record,
                    signature=signature,
                    verified=hmac.compare_digest(signature, expected),
                )
            )
        except Exception:
            rows.append(
                AuditEventRecord(
                    record={"event": "corrupt_entry", "raw": line},
                    signature="",
                    verified=False,
                )
            )
    return rows


def export_audit_events(ctx: "WorkspaceContext", output_path: Path) -> Path:
    rows = read_audit_events(ctx)
    payload = {
        "workspace_id": ctx.workspace_id,
        "workspace_name": ctx.workspace_name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "events": [
            {
                "record": row.record,
                "signature": row.signature,
                "verified": row.verified,
            }
            for row in rows
        ],
    }
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.chmod(output_path, 0o600)
    return output_path


def delete_audit_events(ctx: "WorkspaceContext") -> bool:
    path = _audit_path_for_context(ctx)
    if not path.exists():
        return False
    path.unlink()
    return True


def audit_log_path_for_workspace_dir(workspace_dir: Path) -> Path:
    return workspace_dir / AUDIT_FILENAME


def _audit_path_for_context(ctx: "WorkspaceContext") -> Path:
    return audit_log_path_for_workspace_dir(ctx.vault.path.parent)


def _sign_payload(payload: dict[str, Any], master_key: bytes) -> str:
    hmac_key = derive_hmac_key(master_key)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hmac.new(hmac_key, encoded, hashlib.sha256).hexdigest()


def _secure_opener(path: str, flags: int) -> int:
    return os.open(path, flags, 0o600)
