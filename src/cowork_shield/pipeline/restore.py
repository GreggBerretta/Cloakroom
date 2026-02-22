"""Restoration pipeline with fail-closed verification."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cowork_shield.exceptions import (
    HallucinationDetectedError,
    IncompleteRestorationError,
    IntegrityError,
    PdfInputOnlyError,
    UnsupportedFormatError,
)
from cowork_shield.hallucination.detector import detect_token_anomalies
from cowork_shield.hallucination.formatter import format_hallucination_flags
from cowork_shield.models import now_iso
from cowork_shield.pipeline.anonymize import HANDLER_MAP
from cowork_shield.verification.verifier import IntegrityVerifier
from cowork_shield.workspace.manager import WorkspaceContext


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

        with self._ctx.operation_lock():
            suffix = input_path.suffix.lower()
            if suffix == ".pdf":
                raise PdfInputOnlyError()
            handler_cls = HANDLER_MAP.get(suffix)
            if handler_cls is None:
                raise UnsupportedFormatError(suffix)
            handler = handler_cls()

            all_mappings = self._ctx.token_generator.get_all_mappings()
            hmac_failures = self._verifier.verify_all_hmacs(all_mappings)
            if hmac_failures:
                raise IntegrityError(
                    f"HMAC verification failed for {len(hmac_failures)} mappings. "
                    f"Vault may be corrupted. Restoration aborted.\n"
                    f"Failed tokens: {', '.join(hmac_failures)}"
                )

            reverse_lookup = self._ctx.get_reverse_lookup()
            if not reverse_lookup:
                raise IntegrityError("No mappings found in workspace. Nothing to restore.")

            if output_path is None:
                stem = input_path.stem
                if stem.endswith(".anonymized"):
                    stem = stem[: -len(".anonymized")]
                output_path = input_path.with_stem(stem + ".restored")

            expected_tokens = self._expected_tokens_for_input(input_path)
            input_text = self._verifier.extract_all_text(input_path)
            flags = detect_token_anomalies(
                text=input_text,
                known_tokens=set(reverse_lookup.keys()),
                expected_tokens=expected_tokens or None,
            )
            if flags:
                raise HallucinationDetectedError(
                    flags,
                    details=format_hallucination_flags(flags),
                )

            temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

            try:
                handler.restore(input_path, temp_path, reverse_lookup)

                remaining = self._verifier.scan_for_remaining_tokens(
                    temp_path,
                    reverse_lookup.keys(),
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

            return RestoreResult(
                input_path=input_path,
                output_path=output_path,
                tokens_restored=len(reverse_lookup),
                workspace_name=self._ctx.workspace_name,
                verification_passed=True,
            )

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
