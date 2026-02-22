"""Anonymization pipeline orchestration."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.exceptions import (
    CoWorkShieldError,
    ModelHashMismatchError,
    ReplayMismatchError,
    UnsupportedFormatError,
)
from cowork_shield.handlers.csv_handler import CsvHandler
from cowork_shield.handlers.docx import DocxHandler
from cowork_shield.handlers.pdf_handler import PdfHandler
from cowork_shield.handlers.text_handler import TextHandler
from cowork_shield.handlers.xlsx import XlsxHandler
from cowork_shield.models import Clock, EntityMapping, FileRecord, SystemClock
from cowork_shield.verification.verifier import compute_sha256
from cowork_shield.workspace.manager import WorkspaceContext

HANDLER_MAP = {
    ".xlsx": XlsxHandler,
    ".csv": CsvHandler,
    ".docx": DocxHandler,
    ".txt": TextHandler,
    ".md": TextHandler,
    ".pdf": PdfHandler,
}


@dataclass
class AnonymizeResult:
    """Summary of an anonymization operation."""

    input_path: Path
    output_path: Path
    backup_path: Path | None
    entities_found: int
    tokens_applied: int
    workspace_name: str


class AnonymizePipeline:
    """Orchestrates the full anonymization flow for a file."""

    def __init__(
        self,
        workspace_ctx: WorkspaceContext,
        score_threshold: float = 0.7,
        language: str = "auto",
        hebrew_backend: str | None = None,
        hebrew_stanza_model: str | None = None,
        hebrew_transformer_model: str | None = None,
        *,
        clock: Clock | None = None,
        force_reanonymize: bool = False,
        override_reason: str = "",
        override_user: str = "",
        allow_lossy_xlsx: bool = False,
        pdf_output_format: str = "md",
    ):
        self._ctx = workspace_ctx
        self._clock = clock or SystemClock()
        self._detection = DetectionEngine(
            score_threshold=score_threshold,
            hebrew_backend=hebrew_backend,
            hebrew_stanza_model=hebrew_stanza_model,
            hebrew_transformer_model=hebrew_transformer_model,
        )
        self._language = language
        self._force_reanonymize = force_reanonymize
        self._override_reason = override_reason.strip()
        self._override_user = override_user.strip()
        self._allow_lossy_xlsx = allow_lossy_xlsx
        self._pdf_output_format = (pdf_output_format or "md").strip().lower()

        if self._force_reanonymize and not self._override_reason:
            raise CoWorkShieldError(
                "--force-reanonymize requires a non-empty --reason for auditability."
            )

    def run(
        self,
        input_path: Path,
        output_path: Path | None = None,
    ) -> AnonymizeResult:
        """Anonymize a single file within the workspace context."""
        input_path = input_path.resolve()
        self._ctx.ensure_not_expired()

        with self._ctx.operation_lock():
            suffix = input_path.suffix.lower()
            handler_cls = HANDLER_MAP.get(suffix)
            if handler_cls is None:
                raise UnsupportedFormatError(suffix)

            if suffix == ".xlsx":
                handler = handler_cls(allow_lossy_xlsx=self._allow_lossy_xlsx)
            elif suffix == ".pdf":
                handler = handler_cls(pdf_output_format=self._pdf_output_format)
            else:
                handler = handler_cls()

            if output_path is None:
                if suffix == ".pdf":
                    output_ext = ".docx" if self._pdf_output_format == "docx" else ".md"
                    output_path = input_path.with_name(f"{input_path.stem}.anonymized{output_ext}")
                else:
                    output_path = input_path.with_stem(input_path.stem + ".anonymized")

            backup_path = None
            if suffix == ".xlsx":
                backup_path = input_path.with_suffix(input_path.suffix + ".backup")
                if not backup_path.exists():
                    shutil.copy2(input_path, backup_path)

            input_hash = compute_sha256(input_path)
            model_hash = self._detection.get_model_hash()
            expected_output_hash = ""
            override_events: list[str] = []

            model_lock_key = self._detection.model_lock_key
            locked_model_hash = self._resolve_locked_model_hash(model_lock_key)
            if locked_model_hash and locked_model_hash != model_hash:
                if not self._force_reanonymize:
                    raise ModelHashMismatchError(expected=locked_model_hash, actual=model_hash)
                override_events.append("model_hash_mismatch")

            previous_record = self._find_previous_record(input_path, input_hash)
            if previous_record is not None:
                expected_output_hash = previous_record.file_hash_after
                if previous_record.model_hash and previous_record.model_hash != model_hash:
                    if not self._force_reanonymize:
                        raise ModelHashMismatchError(
                            expected=previous_record.model_hash,
                            actual=model_hash,
                        )
                    override_events.append("previous_record_model_mismatch")

            counters_snapshot, mappings_snapshot = self._ctx.token_generator.export_state()
            file_records_before = list(self._ctx.vault_data.file_records)
            model_hashes_before = dict(self._ctx.vault_data.model_hashes)
            token_counter_before = dict(self._ctx.vault_data.token_counter)
            mappings_before = dict(self._ctx.vault_data.mappings)
            anonymize_count_before = self._ctx.vault_data.anonymize_count
            last_used_before = self._ctx.vault_data.last_used
            token_abi_before = self._ctx.vault_data.token_abi_version

            try:
                records, file_record = handler.anonymize(
                    input_path,
                    output_path,
                    self._detection,
                    self._ctx.token_generator,
                    source_file=input_path.name,
                    language=self._language,
                )
            except Exception:
                self._ctx.token_generator.load_state(counters_snapshot, mappings_snapshot)
                raise

            file_record.model_hash = model_hash
            file_record.applied_tokens = sorted({record.token_text for record in records})
            file_record.previous_output_hash = expected_output_hash

            if expected_output_hash and file_record.file_hash_after != expected_output_hash:
                if not self._force_reanonymize:
                    self._rollback_run(output_path, counters_snapshot, mappings_snapshot)
                    raise ReplayMismatchError(
                        expected=expected_output_hash,
                        actual=file_record.file_hash_after,
                    )
                override_events.append("replay_hash_mismatch")

            if self._force_reanonymize:
                override_events.append("manual_force_reanonymize")
                file_record.reanonymize_override = True
                file_record.override_reason = self._override_reason
                file_record.override_user = self._override_user
                file_record.override_timestamp = self._clock.now_iso()

            if override_events:
                file_record.override_events = sorted(set(override_events))

            counters, mappings = self._ctx.token_generator.export_state()
            self._ctx.vault_data.token_counter = counters
            self._ctx.vault_data.mappings = mappings
            self._ctx.vault_data.file_records.append(file_record)
            self._ctx.vault_data.model_hashes[model_lock_key] = model_hash
            self._ctx.vault_data.token_abi_version = "v2"
            self._ctx.vault_data.anonymize_count += 1
            self._ctx.vault_data.last_used = self._clock.now_iso()

            try:
                self._ctx.persist()
            except Exception:
                self._ctx.token_generator.load_state(counters_snapshot, mappings_snapshot)
                self._ctx.vault_data.file_records = file_records_before
                self._ctx.vault_data.model_hashes = model_hashes_before
                self._ctx.vault_data.token_counter = token_counter_before
                self._ctx.vault_data.mappings = mappings_before
                self._ctx.vault_data.anonymize_count = anonymize_count_before
                self._ctx.vault_data.last_used = last_used_before
                self._ctx.vault_data.token_abi_version = token_abi_before
                if output_path.exists():
                    output_path.unlink()
                raise

            return AnonymizeResult(
                input_path=input_path,
                output_path=output_path,
                backup_path=backup_path,
                entities_found=file_record.entities_found,
                tokens_applied=file_record.tokens_applied,
                workspace_name=self._ctx.workspace_name,
            )

    def _find_previous_record(self, input_path: Path, input_hash: str) -> FileRecord | None:
        wanted_path = str(input_path)
        for record in reversed(self._ctx.vault_data.file_records):
            if record.file_path == wanted_path and record.file_hash_before == input_hash:
                return record
        return None

    def _rollback_run(
        self,
        output_path: Path,
        counters_snapshot: dict[str, int],
        mappings_snapshot: dict[str, EntityMapping],
    ) -> None:
        self._ctx.token_generator.load_state(counters_snapshot, mappings_snapshot)
        if output_path.exists():
            output_path.unlink()

    def _resolve_locked_model_hash(self, model_lock_key: str) -> str:
        model_hashes = self._ctx.vault_data.model_hashes
        if model_lock_key in model_hashes:
            return model_hashes[model_lock_key]

        legacy_keys = getattr(self._detection, "legacy_model_lock_keys", ())
        for legacy_key in legacy_keys:
            if legacy_key in model_hashes:
                return model_hashes[legacy_key]
        return ""
