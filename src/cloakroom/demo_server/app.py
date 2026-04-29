"""FastAPI backend for the local Cloakroom killer demo."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
import re
import shutil
import threading
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from cloakroom.demo import load_sample
from cloakroom.detection.demo_rules import build_default_demo_ruleset
from cloakroom.governance.reporting import read_sanitization_reports
from cloakroom.logging.audit import read_audit_events
from cloakroom.models import VaultData, now_iso
from cloakroom.pipeline.anonymize import AnonymizePipeline
from cloakroom.pipeline.restore import RestorePipeline
from cloakroom.pipeline.ui_api import sanitize_ui_error
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext

DEFAULT_DEMO_DIR = Path.home() / ".cloakroom" / "demo_server"
DEMO_WORKSPACE_ID = "cloakroom-demo"
DEMO_WORKSPACE_NAME = "Cloakroom Demo"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
LOCAL_TEST_CLIENTS = frozenset({"testclient"})
TOKEN_RE = re.compile(r"\[[A-Z][A-Z0-9_]*_\d{5}\]")
DEMO_SAMPLE_LANGUAGES = {
    "customer_escalation_en.md": "en",
    "customer_escalation_he.md": "he",
    "customer_escalation_mixed.md": "auto",
}
ENGLISH_SAMPLE_MARKERS = [
    "Sarah Morgan",
    "Acme Health",
    "sarah.morgan@acmehealth.eu",
    "Project Lantern",
    "EU-CUST-88421",
    "$2.4M",
    "18 percent discount",
    "+44 20 7946 0182",
    "15 Farringdon Street, London",
    "Q3 churn containment plan",
    "pre-acquisition integration risk",
]
HEBREW_SAMPLE_MARKERS = [
    "moshe.levy@acmehealth.co.il",
    "312345674",
    "050-123-4567",
    "12-345-6789012",
]


class LoadSampleRequest(BaseModel):
    name: str = "customer_escalation_en.md"


class ShieldRequest(BaseModel):
    text: str = Field(default="", description="Original local text to shield.")
    sample_name: str = "customer_escalation_en.md"
    language: str | None = None


class RestoreRequest(BaseModel):
    text: str = Field(default="", description="Tokenized AI response to restore.")


class DemoRuntime:
    """Mutable, single-workspace runtime for the local demo server."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = (base_dir or DEFAULT_DEMO_DIR).expanduser().resolve()
        self._lock = threading.RLock()
        self.ctx: WorkspaceContext
        self.reset()

    def reset(self) -> dict[str, Any]:
        with self._lock:
            if self.base_dir.exists():
                shutil.rmtree(self.base_dir)
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self.ctx = self._new_context()
            self.ctx.persist()
            return self.trust_center()

    def load_sample(self, name: str = "customer_escalation_en.md") -> dict[str, Any]:
        sample_name = _validate_sample_name(name)
        original = load_sample(sample_name)
        return {
            "ok": True,
            "sample_name": sample_name,
            "language": DEMO_SAMPLE_LANGUAGES[sample_name],
            "original_text": original,
            "sensitive_markers": _sample_markers(sample_name),
        }

    def shield(
        self,
        text: str,
        *,
        sample_name: str = "customer_escalation_en.md",
        language: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            sample_name = _validate_sample_name(sample_name)
            effective_text = text or load_sample(sample_name)
            effective_language = language or DEMO_SAMPLE_LANGUAGES[sample_name]
            input_path = self.base_dir / "original.md"
            safe_path = self.base_dir / "ai_safe.md"
            input_path.write_text(effective_text, encoding="utf-8")

            result = AnonymizePipeline(
                self.ctx,
                score_threshold=0.5,
                demo_ruleset=build_default_demo_ruleset(),
                language=effective_language,
            ).run(input_path, safe_path)
            safe_text = safe_path.read_text(encoding="utf-8")
            latest_report = _latest_report(self.ctx)
            markers = _sample_markers(sample_name)
            leaked_markers = [marker for marker in markers if marker in safe_text]
            simulated = simulated_ai_response(safe_text)
            mutated = mutated_ai_response(simulated)

            return {
                "ok": True,
                "operation": "shield",
                "sample_name": sample_name,
                "language": effective_language,
                "original_text": effective_text,
                "ai_safe_text": safe_text,
                "simulated_ai_response": simulated,
                "mutated_ai_response": mutated,
                "entities_found": result.entities_found,
                "tokens_applied": result.tokens_applied,
                "review_items": _review_items(self.ctx, safe_text),
                "entity_counts": latest_report.get("entity_counts", {}),
                "report": latest_report,
                "leak_check": {
                    "known_sensitive_items": len(markers),
                    "shielded_items": len(markers) - len(leaked_markers),
                    "leaked_items": len(leaked_markers),
                },
                "trust_center": self.trust_center(),
            }

    def restore(self, text: str) -> dict[str, Any]:
        with self._lock:
            response_path = self.base_dir / "ai_response.md"
            restored_path = self.base_dir / "restored.md"
            if restored_path.exists():
                restored_path.unlink()
            response_path.write_text(text, encoding="utf-8")

            try:
                result = RestorePipeline(self.ctx).run(response_path, restored_path)
            except Exception as exc:  # noqa: BLE001 - converted to UI-safe structured payload.
                code, message = sanitize_ui_error(exc)
                return {
                    "ok": False,
                    "operation": "restore",
                    "restore_blocked": True,
                    "error": {
                        "code": code,
                        "message": message,
                    },
                    "restored_text": "",
                    "trust_center": self.trust_center(),
                }

            restored_text = restored_path.read_text(encoding="utf-8")
            latest_report = _latest_report(self.ctx)
            return {
                "ok": True,
                "operation": "restore",
                "restore_blocked": False,
                "restored_text": restored_text,
                "tokens_restored": result.tokens_restored,
                "verification_passed": result.verification_passed,
                "entity_counts": latest_report.get("entity_counts", {}),
                "report": latest_report,
                "trust_center": self.trust_center(),
            }

    def trust_center(self) -> dict[str, Any]:
        with self._lock:
            reports = read_sanitization_reports(self.ctx, limit=50)
            audit_rows = read_audit_events(self.ctx)[-50:]
            vault_data = self.ctx.vault_data
            expires_at = _expires_at(vault_data.created_at, vault_data.ttl_hours)
            return {
                "ok": True,
                "workspace": {
                    "workspace_id": self.ctx.workspace_id,
                    "workspace_name": self.ctx.workspace_name,
                    "created_at": vault_data.created_at,
                    "last_used": vault_data.last_used,
                    "ttl_hours": vault_data.ttl_hours,
                    "expires_at": expires_at,
                },
                "vault": {
                    "encrypted": self.ctx.vault.exists(),
                    "local_only": True,
                    "mappings_count": len(vault_data.mappings),
                    "file_records_count": len(vault_data.file_records),
                    "token_abi_version": vault_data.token_abi_version,
                    "self_destruct_on_restore": vault_data.self_destruct_on_restore,
                },
                "activity": {
                    "anonymize_count": vault_data.anonymize_count,
                    "restore_count": vault_data.restore_count,
                    "abort_count": vault_data.abort_count,
                },
                "reports": reports,
                "audit_events": [
                    {
                        "record": row.record,
                        "signature": row.signature,
                        "verified": row.verified,
                    }
                    for row in audit_rows
                ],
                "local_only_proof": {
                    "bind_host": "127.0.0.1",
                    "external_ai_calls": 0,
                    "demo_ai_response": "simulated",
                    "original_values_in_reports": False,
                },
                "policy": [
                    "Original values stay in the local encrypted vault.",
                    "Only tokenized AI-safe text is intended to leave the machine.",
                    "Restore fails closed if AI mutates, invents, or drops protected tokens.",
                    "Audit and report surfaces use hashes and opaque labels, not raw filenames.",
                ],
            }

    def _new_context(self) -> WorkspaceContext:
        master_key = generate_master_key()
        vault_data = VaultData(
            workspace_id=DEMO_WORKSPACE_ID,
            workspace_name=DEMO_WORKSPACE_NAME,
            created_at=now_iso(),
            updated_at=now_iso(),
            ttl_hours=24,
        )
        return WorkspaceContext(
            workspace_id=DEMO_WORKSPACE_ID,
            workspace_name=DEMO_WORKSPACE_NAME,
            vault=Vault(self.base_dir / "vault.enc"),
            vault_data=vault_data,
            token_generator=TokenGenerator(derive_hmac_key(master_key)),
            master_key=master_key,
        )


def create_app(runtime: DemoRuntime | None = None) -> FastAPI:
    demo_runtime = runtime or DemoRuntime()
    app = FastAPI(title="Cloakroom Demo Server", version="0.1.0")
    static_dir = resources.files(__package__).joinpath("static")
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.middleware("http")
    async def _local_only_guard(request: Request, call_next):
        client_host = request.client.host if request.client else ""
        if client_host and client_host not in LOOPBACK_HOSTS and client_host not in LOCAL_TEST_CLIENTS:
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "error": {
                        "code": "LocalOnly",
                        "message": "Cloakroom demo server accepts local requests only.",
                    },
                },
            )
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "cloakroom-demo-server",
            "local_only": True,
        }

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def demo_ui() -> HTMLResponse:
        html = static_dir.joinpath("index.html").read_text(encoding="utf-8")
        return HTMLResponse(html)

    @app.post("/api/demo/load-sample")
    def load_demo_sample(request: LoadSampleRequest) -> dict[str, Any]:
        return demo_runtime.load_sample(request.name)

    @app.post("/api/demo/reset")
    def reset_demo() -> dict[str, Any]:
        return {
            "ok": True,
            "reset": True,
            "trust_center": demo_runtime.reset(),
        }

    @app.post("/api/shield")
    def shield(request: ShieldRequest) -> dict[str, Any]:
        return demo_runtime.shield(
            request.text,
            sample_name=request.sample_name,
            language=request.language,
        )

    @app.post("/api/restore")
    def restore(request: RestoreRequest) -> dict[str, Any]:
        return demo_runtime.restore(request.text)

    @app.get("/api/trust-center")
    def trust_center() -> dict[str, Any]:
        return demo_runtime.trust_center()

    return app


def simulated_ai_response(safe_text: str) -> str:
    lines = [line for line in safe_text.strip().splitlines() if line.strip()]
    first_line = lines[0] if lines else ""
    subject = first_line.split(" at ")[0] if " at " in first_line else "[PERSON_00001]"
    return (
        "Risk summary:\n"
        f"- The {subject} escalation is high priority.\n"
        "- Account contract size is significant.\n\n"
        "Draft client response:\n"
        f"{first_line}\n"
        "We acknowledge the renewal concerns and will follow up shortly.\n"
    )


def mutated_ai_response(ai_response: str) -> str:
    return ai_response.replace("[PERSON_00001]", "[PERSON_001]", 1)


def validate_bind_host(host: str) -> str:
    normalized = (host or "").strip().lower()
    if normalized not in LOOPBACK_HOSTS:
        raise ValueError("Cloakroom demo server must bind to 127.0.0.1, ::1, or localhost.")
    return normalized


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local Cloakroom demo backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    host = validate_bind_host(args.host)

    import uvicorn

    uvicorn.run(create_app(), host=host, port=args.port)


def _validate_sample_name(name: str) -> str:
    sample_name = (name or "customer_escalation_en.md").strip()
    if sample_name not in DEMO_SAMPLE_LANGUAGES:
        raise HTTPException(status_code=404, detail=f"Unknown demo sample: {sample_name}")
    return sample_name


def _sample_markers(sample_name: str) -> list[str]:
    if sample_name == "customer_escalation_en.md":
        return list(ENGLISH_SAMPLE_MARKERS)
    if sample_name == "customer_escalation_he.md":
        return list(HEBREW_SAMPLE_MARKERS)
    if sample_name == "customer_escalation_mixed.md":
        return [*ENGLISH_SAMPLE_MARKERS, *HEBREW_SAMPLE_MARKERS]
    return []


def _review_items(ctx: WorkspaceContext, current_text: str = "") -> list[dict[str, Any]]:
    current_tokens = set(TOKEN_RE.findall(current_text)) if current_text else set()
    items = []
    for mapping in sorted(
        ctx.vault_data.mappings.values(),
        key=lambda item: (item.first_seen, item.token.token_text),
    ):
        token_text = mapping.token.token_text
        if current_tokens and token_text not in current_tokens:
            continue
        items.append(
            {
                "risk_type": _risk_type_label(mapping.entity_type.value),
                "group": _risk_group(mapping.entity_type.value),
                "masked_value": _mask_value(mapping.original_value),
                "token": token_text,
                "location": _source_location(mapping.source_files),
                "confidence": _confidence_label(mapping.entity_type.value),
                "action": "Shielded",
            }
        )
    return items


def _risk_type_label(entity_type: str) -> str:
    return entity_type.replace("_", " ").title()


def _risk_group(entity_type: str) -> str:
    if entity_type in {"PERSON", "EMAIL", "PHONE", "ADDRESS_LINE", "HE_PERSON"}:
        return "Personal data"
    if entity_type in {"TEUDAT_ZEHUT", "IL_PHONE", "IL_ADDRESS", "IL_BANK_ACCOUNT"}:
        return "PII / regulated identifiers"
    if entity_type in {"ORG", "CUSTOMER_ID"}:
        return "Customer confidential"
    if entity_type in {"PROJECT", "STRATEGY"}:
        return "Strategic information"
    if entity_type in {"CONTRACT_VALUE", "PRICING_TERM"}:
        return "Financial and contract data"
    return "Custom rules"


def _confidence_label(entity_type: str) -> str:
    if entity_type in {
        "PROJECT",
        "STRATEGY",
        "CONTRACT_VALUE",
        "PRICING_TERM",
        "CUSTOMER_ID",
        "ADDRESS_LINE",
    }:
        return "Rule match"
    return "High"


def _source_location(source_files: list[str]) -> str:
    if not source_files:
        return "Current input"
    return Path(source_files[0]).suffix.lstrip(".").upper() or "Current input"


def _mask_value(value: str) -> str:
    cleaned = " ".join((value or "").split())
    if not cleaned:
        return "***"
    if "@" in cleaned:
        local, _, domain = cleaned.partition("@")
        return f"{local[:4]}...@...{domain[-3:]}"
    if len(cleaned) <= 4:
        return "***"
    if len(cleaned) <= 10:
        return f"{cleaned[:2]}...{cleaned[-2:]}"
    return f"{cleaned[:6]}...{cleaned[-4:]}"


def _latest_report(ctx: WorkspaceContext) -> dict[str, Any]:
    rows = read_sanitization_reports(ctx, limit=1)
    return rows[-1] if rows else {}


def _expires_at(created_at: str, ttl_hours: int) -> str:
    if ttl_hours <= 0:
        return ""
    try:
        created = datetime.fromisoformat(created_at)
    except ValueError:
        return ""
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (created + timedelta(hours=ttl_hours)).isoformat()
