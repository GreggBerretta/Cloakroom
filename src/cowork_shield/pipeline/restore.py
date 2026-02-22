"""Restoration pipeline with fail-closed verification."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cowork_shield.exceptions import (
    IncompleteRestorationError,
    IntegrityError,
    UnsupportedFormatError,
)
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
    """Orchestrates the full restoration flow with fail-closed verification.

    FAIL-CLOSED DESIGN: If ANY verification check fails, the entire
    restoration is aborted. No partial restores ever occur.

    Flow:
    1. Verify all HMAC tags on all mappings (pre-flight)
    2. Build reverse lookup (token -> original)
    3. Restore to a TEMPORARY file (never directly to output)
    4. Scan temp file for remaining tokens (post-flight)
    5. If all checks pass: rename temp file to output
    6. If any check fails: delete temp file, abort
    """

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

        # 1. Validate format
        suffix = input_path.suffix.lower()
        handler_cls = HANDLER_MAP.get(suffix)
        if handler_cls is None:
            raise UnsupportedFormatError(suffix)
        handler = handler_cls()

        # 2. PRE-FLIGHT: verify ALL HMAC tags before any work
        all_mappings = self._ctx.token_generator.get_all_mappings()

        hmac_failures = self._verifier.verify_all_hmacs(all_mappings)
        if hmac_failures:
            raise IntegrityError(
                f"HMAC verification failed for {len(hmac_failures)} mappings. "
                f"Vault may be corrupted. Restoration aborted.\n"
                f"Failed tokens: {', '.join(hmac_failures)}"
            )

        # 3. Build reverse lookup
        reverse_lookup = self._ctx.get_reverse_lookup()

        if not reverse_lookup:
            raise IntegrityError(
                "No mappings found in workspace. Nothing to restore."
            )

        # 4. Determine output path
        if output_path is None:
            stem = input_path.stem
            if stem.endswith(".anonymized"):
                stem = stem[: -len(".anonymized")]
            output_path = input_path.with_stem(stem + ".restored")

        # 5. Restore to TEMP file (not directly to output)
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

        try:
            handler.restore(input_path, temp_path, reverse_lookup)

            # 6. POST-FLIGHT: scan for remaining tokens
            remaining = self._verifier.scan_for_remaining_tokens(
                temp_path, reverse_lookup.keys()
            )
            if remaining:
                raise IncompleteRestorationError(remaining)

            # 7. All checks passed — commit
            if output_path.exists():
                output_path.unlink()
            os.rename(str(temp_path), str(output_path))

        except Exception:
            # Clean up temp file on any failure
            if temp_path.exists():
                temp_path.unlink()
            raise

        return RestoreResult(
            input_path=input_path,
            output_path=output_path,
            tokens_restored=len(reverse_lookup),
            workspace_name=self._ctx.workspace_name,
            verification_passed=True,
        )
