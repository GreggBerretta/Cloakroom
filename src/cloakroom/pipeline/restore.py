"""Restoration pipeline with fail-closed verification."""

from __future__ import annotations

import logging as py_logging
import os
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from cloakroom.exceptions import (
    HallucinationDetectedError,
    IncompleteRestorationError,
    IntegrityError,
    PdfInputOnlyError,
    UnsupportedFormatError,
)
from cloakroom.governance.reporting import (
    append_sanitization_report,
    build_restore_entity_counts,
)
from cloakroom.hallucination.detector import detect_token_anomalies
from cloakroom.hallucination.formatter import format_hallucination_flags
from cloakroom.logging import append_audit_event, log_event
from cloakroom.models import now_iso
from cloakroom.pipeline.anonymize import HANDLER_MAP
from cloakroom.verification.verifier import IntegrityVerifier
from cloakroom.workspace.manager import WorkspaceContext


@dataclass
class RestoreResult:
    """Summary of a restoration operation."""

    input_path: Path
    output_path: Path
    tokens_restored: int
    workspace_name: str
    verification_passed: bool


class RestorePipeline:
    """Orchestrates the full restoration flow with fail-closed verification."""

    def __init__(self, workspace_ctx: WorkspaceContext):
        self._ctx = workspace_ctx
        self._verifier = IntegrityVerifier(workspace_ctx.token_generator)

    def run(
        self,
        input_path: Path,
        output_path: Path | None = None,
    ) -> RestoreResult:
        """Restore an anonymized file to its original form."""
        input_path = input_path.resolve()
        self._ctx.ensure_not_expired()
        started = perf_counter()

        try:
            with self._ctx.operation_lock():
                suffix = input_path.suffix.lower()
                if suffix == ".pdf":
                    raise PdfInputOnlyError()
                handler_cls = HANDLER_MAP.get(suffix)
                if handler_cls is None:
                    raise UnsupportedFormatError(suffix)
                handler = handler_cls()

                log_event(
                    "engine",
                    level=20,
                    event="restore_start",
                    message="Starting restore pipeline",
                    workspace_id=self._ctx.workspace_id,
                    metadata={"file_path": str(input_path), "file_ext": suffix},
                )

                all_mappings = self._ctx.token_generator.get_all_mappings()
                if not all_mappings:
                    raise IntegrityError("No mappings found in workspace. Nothing to restore.")

                if output_path is None:
                    stem = input_path.stem
                    if stem.endswith(".anonymized"):
                        stem = stem[: -len(".anonymized")]
                    output_path = input_path.with_stem(stem + ".restored")

                expected_tokens = self._expected_tokens_for_input(input_path)
                input_text = self._verifier.extract_all_text(input_path)
                known_tokens = {
                    mapping.token.token_text
                    for mapping in all_mappings.values()
                }

                observed_tokens = self._verifier.extract_token_matches(input_text)
                flags = detect_token_anomalies(
                    text=input_text,
                    known_tokens=known_tokens,
                    expected_tokens=expected_tokens or None,
                )
                if flags:
                    raise HallucinationDetectedError(
                        flags,
                        details=format_hallucination_flags(flags),
                    )

                active_tokens = self._verifier.resolve_known_tokens(observed_tokens, known_tokens)
                hmac_failures = self._verifier.verify_hmacs_for_token_subset(
                    all_mappings,
                    active_tokens,
                )
                if hmac_failures:
                    raise IntegrityError(
                        f"HMAC verification failed for {len(hmac_failures)} mappings. "
                        f"Vault may be corrupted. Restoration aborted.\n"
                        f"Failed tokens: {', '.join(hmac_failures)}"
                    )

                reverse_lookup = {
                    mapping.token.token_text: mapping.original_value
                    for mapping in all_mappings.values()
                    if mapping.token.token_text in active_tokens
                }

                temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

                try:
                    handler.restore(input_path, temp_path, reverse_lookup)

                    remaining = self._verifier.scan_for_remaining_tokens(
                        temp_path,
                        active_tokens,
                    )
                    if remaining:
                        raise IncompleteRestorationError(remaining)

                    if output_path.exists():
                        output_path.unlink()
                    os.rename(str(temp_path), str(output_path))
                except Exception:
                    if temp_path.exists():
                        temp_path.unlink()
                    self._ctx.vault_data.abort_count += 1
                    try:
                        self._ctx.persist()
                    except Exception:
                        pass
                    raise

                self._ctx.vault_data.restore_count += 1
                self._ctx.vault_data.last_used = now_iso()
                self._ctx.persist()

                self_destruct_enabled = bool(self._ctx.vault_data.self_destruct_on_restore)
                if self_destruct_enabled:
                    self._ctx.token_generator.load_state({}, {})
                    self._ctx.vault_data.mappings = {}
                    self._ctx.vault_data.token_counter = {}
                    self._ctx.vault_data.file_records = []
                    self._ctx.vault_data.last_used = now_iso()
                    self._ctx.persist()
                    append_audit_event(
                        self._ctx,
                        event="workspace_self_destruct_after_restore",
                        fields={"file_path": str(input_path)},
                    )

                duration_ms = int((perf_counter() - started) * 1000)
                log_event(
                    "engine",
                    level=py_logging.INFO,
                    event="restore_complete",
                    message="Restore complete",
                    workspace_id=self._ctx.workspace_id,
                    metadata={
                        "file_path": str(input_path),
                        "file_ext": suffix,
                        "duration_ms": duration_ms,
                        "tokens_restored": len(active_tokens),
                        "integrity_check": True,
                        "self_destruct_on_restore": self_destruct_enabled,
                    },
                )
                append_audit_event(
                    self._ctx,
                    event="file_restored",
                    fields={
                        "file_path": str(input_path),
                        "file_ext": suffix,
                        "duration_ms": duration_ms,
                        "integrity_check": True,
                    },
                )

                try:
                    token_type_map = {
                        mapping.token.token_text: mapping.entity_type
                        for mapping in all_mappings.values()
                    }
                    token_original_map = {
                        mapping.token.token_text: mapping.original_value
                        for mapping in all_mappings.values()
                    }
                    append_sanitization_report(
                        self._ctx,
                        operation="restore",
                        file_path=str(input_path),
                        file_ext=suffix,
                        duration_ms=duration_ms,
                        language="auto",
                        entity_counts=build_restore_entity_counts(
                            token_texts=active_tokens,
                            token_to_entity_type=token_type_map,
                            token_to_original=token_original_map,
                        ),
                        entities_total=len(active_tokens),
                        tokens_restored=len(active_tokens),
                        metadata={"self_destruct_on_restore": self_destruct_enabled},
                    )
                except Exception as report_exc:  # noqa: BLE001
                    log_event(
                        "engine",
                        level=py_logging.WARNING,
                        event="sanitization_report_failed",
                        message="Failed to append sanitization report",
                        workspace_id=self._ctx.workspace_id,
                        metadata={"file_path": str(input_path)},
                        exc=report_exc,
                    )

                return RestoreResult(
                    input_path=input_path,
                    output_path=output_path,
                    tokens_restored=len(active_tokens),
                    workspace_name=self._ctx.workspace_name,
                    verification_passed=True,
                )
        except Exception as exc:
            log_event(
                "engine",
                level=py_logging.ERROR,
                event="restore_failed",
                message="Restore failed",
                workspace_id=self._ctx.workspace_id,
                metadata={"file_path": str(input_path)},
                exc=exc,
            )
            if isinstance(exc, IntegrityError):
                append_audit_event(
                    self._ctx,
                    event="integrity_failure",
                    fields={
                        "file_path": str(input_path),
                        "failure_type": exc.__class__.__name__,
                    },
                )
            raise

    def _expected_tokens_for_input(self, input_path: Path) -> set[str]:
        input_raw = str(input_path)
        input_resolved = str(input_path.resolve())

        for file_record in reversed(self._ctx.vault_data.file_records):
            record_path_raw = file_record.anonymized_path
            if record_path_raw in (input_raw, input_resolved):
                return set(file_record.applied_tokens)

            try:
                record_resolved = str(Path(record_path_raw).resolve())
            except Exception:
                record_resolved = ""
            if record_resolved in (input_raw, input_resolved):
                return set(file_record.applied_tokens)

        return set()
