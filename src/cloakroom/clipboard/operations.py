"""Clipboard anonymize/restore workflows."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from cloakroom.detection.engine import DetectionEngine
from cloakroom.exceptions import (
    CloakroomError,
    HallucinationDetectedError,
    IncompleteRestorationError,
    IntegrityError,
    ModelHashMismatchError,
    ReplayMismatchError,
)
from cloakroom.governance.reporting import (
    append_sanitization_report,
    build_anonymize_entity_counts,
    build_restore_entity_counts,
)
from cloakroom.hallucination.detector import detect_token_anomalies
from cloakroom.hallucination.formatter import format_hallucination_flags
from cloakroom.models import FileRecord, now_iso
from cloakroom.tokenizer.patterns import ANY_TOKEN_PATTERN
from cloakroom.tokenizer.replacer import TextReplacer
from cloakroom.verification.verifier import IntegrityVerifier
from cloakroom.workspace.manager import WorkspaceContext

CLIPBOARD_FILE_ID = "<clipboard>"


@dataclass
class ClipboardShieldResult:
    entities_found: int
    tokens_applied: int
    model_hash: str
    anonymized_text: str = ""


@dataclass
class ClipboardRestoreResult:
    tokens_restored: int
    verification_passed: bool
    restored_text: str = ""


def shield_clipboard(
    workspace_ctx: WorkspaceContext,
    *,
    score_threshold: float = 0.7,
    detection_mode: str = "balanced",
    language: str = "auto",
    hebrew_backend: str | None = None,
    hebrew_stanza_model: str | None = None,
    hebrew_transformer_model: str | None = None,
    force_reanonymize: bool = False,
    override_reason: str = "",
    override_user: str = "",
) -> ClipboardShieldResult:
    """Read clipboard, anonymize text in-memory, and overwrite clipboard."""
    return _shield_text(
        workspace_ctx,
        text_reader=_pbpaste,
        text_writer=_pbcopy,
        score_threshold=score_threshold,
        detection_mode=detection_mode,
        language=language,
        hebrew_backend=hebrew_backend,
        hebrew_stanza_model=hebrew_stanza_model,
        hebrew_transformer_model=hebrew_transformer_model,
        force_reanonymize=force_reanonymize,
        override_reason=override_reason,
        override_user=override_user,
    )


def shield_clipboard_text(
    workspace_ctx: WorkspaceContext,
    text: str,
    *,
    score_threshold: float = 0.7,
    detection_mode: str = "balanced",
    language: str = "auto",
    hebrew_backend: str | None = None,
    hebrew_stanza_model: str | None = None,
    hebrew_transformer_model: str | None = None,
    force_reanonymize: bool = False,
    override_reason: str = "",
    override_user: str = "",
) -> ClipboardShieldResult:
    """Anonymize caller-provided clipboard text without touching the system clipboard."""
    return _shield_text(
        workspace_ctx,
        text_reader=lambda: text,
        text_writer=None,
        score_threshold=score_threshold,
        detection_mode=detection_mode,
        language=language,
        hebrew_backend=hebrew_backend,
        hebrew_stanza_model=hebrew_stanza_model,
        hebrew_transformer_model=hebrew_transformer_model,
        force_reanonymize=force_reanonymize,
        override_reason=override_reason,
        override_user=override_user,
    )


def _shield_text(
    workspace_ctx: WorkspaceContext,
    *,
    text_reader: Callable[[], str],
    text_writer: Callable[[str], None] | None,
    score_threshold: float,
    detection_mode: str,
    language: str,
    hebrew_backend: str | None,
    hebrew_stanza_model: str | None,
    hebrew_transformer_model: str | None,
    force_reanonymize: bool,
    override_reason: str,
    override_user: str,
) -> ClipboardShieldResult:
    started = perf_counter()
    workspace_ctx.ensure_not_expired()
    with workspace_ctx.operation_lock():
        text = text_reader()
        if not text.strip():
            raise CloakroomError("Clipboard is empty.")

        if force_reanonymize and not override_reason.strip():
            raise CloakroomError("--force-reanonymize requires --reason.")

        detection = _create_detection_engine(
            score_threshold=score_threshold,
            detection_mode=detection_mode,
            hebrew_backend=hebrew_backend,
            hebrew_stanza_model=hebrew_stanza_model,
            hebrew_transformer_model=hebrew_transformer_model,
        )
        replacer = TextReplacer()
        input_hash = _sha256_text(text)
        model_hash = detection.get_model_hash()
        override_events: list[str] = []

        model_lock_key = detection.model_lock_key
        locked_model_hash = _resolve_locked_model_hash(workspace_ctx, detection, model_lock_key)
        if locked_model_hash and locked_model_hash != model_hash:
            if not force_reanonymize:
                raise ModelHashMismatchError(expected=locked_model_hash, actual=model_hash)
            override_events.append("model_hash_mismatch")

        previous_record = _find_previous_clipboard_record(workspace_ctx, input_hash)
        expected_output_hash = previous_record.file_hash_after if previous_record else ""
        if previous_record and previous_record.model_hash and previous_record.model_hash != model_hash:
            if not force_reanonymize:
                raise ModelHashMismatchError(
                    expected=previous_record.model_hash,
                    actual=model_hash,
                )
            override_events.append("previous_record_model_mismatch")

        counters_snapshot, mappings_snapshot = workspace_ctx.token_generator.export_state()

        entities = _detect_in_cell(
            detection,
            text=text,
            source_id="clipboard:0",
            language=language,
        )
        anonymized_text, records = replacer.replace_entities(
            text,
            entities,
            workspace_ctx.token_generator,
            source_file="clipboard",
        )
        output_hash = _sha256_text(anonymized_text)

        if expected_output_hash and output_hash != expected_output_hash:
            if not force_reanonymize:
                workspace_ctx.token_generator.load_state(counters_snapshot, mappings_snapshot)
                raise ReplayMismatchError(expected=expected_output_hash, actual=output_hash)
            override_events.append("replay_hash_mismatch")

        if text_writer is not None:
            text_writer(anonymized_text)

        file_record = FileRecord(
            file_path=CLIPBOARD_FILE_ID,
            file_hash_before=input_hash,
            file_hash_after=output_hash,
            anonymized_path=CLIPBOARD_FILE_ID,
            entities_found=len(entities),
            tokens_applied=len(records),
            timestamp=now_iso(),
            format="clipboard",
            model_hash=model_hash,
            applied_tokens=sorted({record.token_text for record in records}),
            previous_output_hash=expected_output_hash,
        )

        if force_reanonymize:
            override_events.append("manual_force_reanonymize")
            file_record.reanonymize_override = True
            file_record.override_reason = override_reason.strip()
            file_record.override_user = override_user.strip()
            file_record.override_timestamp = now_iso()

        if override_events:
            file_record.override_events = sorted(set(override_events))

        counters, mappings = workspace_ctx.token_generator.export_state()
        workspace_ctx.vault_data.token_counter = counters
        workspace_ctx.vault_data.mappings = mappings
        workspace_ctx.vault_data.file_records.append(file_record)
        workspace_ctx.vault_data.model_hashes[model_lock_key] = model_hash
        workspace_ctx.vault_data.anonymize_count += 1
        workspace_ctx.vault_data.last_used = now_iso()
        workspace_ctx.vault_data.token_abi_version = "v2"
        workspace_ctx.persist()

        duration_ms = int((perf_counter() - started) * 1000)
        append_sanitization_report(
            workspace_ctx,
            operation="clipboard_anonymize",
            file_path=CLIPBOARD_FILE_ID,
            file_ext="clipboard",
            file_hash=input_hash,
            duration_ms=duration_ms,
            language=language,
            entity_counts=build_anonymize_entity_counts(records, language=language),
            entities_total=len(entities),
            tokens_applied=len(records),
            metadata={
                "force_reanonymize": bool(force_reanonymize),
            },
        )

        return ClipboardShieldResult(
            entities_found=len(entities),
            tokens_applied=len(records),
            model_hash=model_hash,
            anonymized_text=anonymized_text,
        )


def restore_clipboard(workspace_ctx: WorkspaceContext) -> ClipboardRestoreResult:
    """Read clipboard tokenized text, restore originals, and overwrite clipboard."""
    return _restore_text(
        workspace_ctx,
        text_reader=_pbpaste,
        text_writer=_pbcopy,
    )


def restore_clipboard_text(
    workspace_ctx: WorkspaceContext,
    tokenized_text: str,
) -> ClipboardRestoreResult:
    """Restore caller-provided clipboard text without touching the system clipboard."""
    return _restore_text(
        workspace_ctx,
        text_reader=lambda: tokenized_text,
        text_writer=None,
    )


def _restore_text(
    workspace_ctx: WorkspaceContext,
    *,
    text_reader: Callable[[], str],
    text_writer: Callable[[str], None] | None,
) -> ClipboardRestoreResult:
    started = perf_counter()
    workspace_ctx.ensure_not_expired()
    with workspace_ctx.operation_lock():
        tokenized_text = text_reader()
        if not tokenized_text.strip():
            raise CloakroomError("Clipboard is empty.")

        verifier = IntegrityVerifier(workspace_ctx.token_generator)
        hmac_failures = verifier.verify_all_hmacs(workspace_ctx.token_generator.get_all_mappings())
        if hmac_failures:
            raise IntegrityError(
                f"HMAC verification failed for {len(hmac_failures)} mappings. "
                f"Failed tokens: {', '.join(hmac_failures)}"
            )

        reverse_lookup = workspace_ctx.get_reverse_lookup()
        if not reverse_lookup:
            raise IntegrityError("No mappings found in workspace. Nothing to restore.")

        expected_tokens = _expected_clipboard_tokens(workspace_ctx)
        known_tokens = set(reverse_lookup.keys())
        observed_tokens = verifier.extract_token_matches(tokenized_text)
        active_tokens = verifier.resolve_known_tokens(observed_tokens, known_tokens)
        flags = detect_token_anomalies(
            text=tokenized_text,
            known_tokens=known_tokens,
            expected_tokens=expected_tokens or None,
        )
        if flags:
            raise HallucinationDetectedError(flags, details=format_hallucination_flags(flags))

        replacer = TextReplacer()
        restored = replacer.restore_tokens(tokenized_text, reverse_lookup)

        remaining = []
        known = set(reverse_lookup.keys())
        for match in ANY_TOKEN_PATTERN.finditer(restored):
            token = match.group(0)
            canonical = token[1:-1] if token.startswith("[") and token.endswith("]") else token
            if token in known or canonical in known or f"[{canonical}]" in known:
                remaining.append(token)
        if remaining:
            raise IncompleteRestorationError(sorted(set(remaining)))

        if text_writer is not None:
            text_writer(restored)

        workspace_ctx.vault_data.restore_count += 1
        workspace_ctx.vault_data.last_used = now_iso()
        workspace_ctx.persist()

        all_mappings = workspace_ctx.token_generator.get_all_mappings()
        token_type_map = {
            mapping.token.token_text: mapping.entity_type
            for mapping in all_mappings.values()
        }
        token_original_map = {
            mapping.token.token_text: mapping.original_value
            for mapping in all_mappings.values()
        }

        self_destruct_enabled = bool(workspace_ctx.vault_data.self_destruct_on_restore)
        if self_destruct_enabled:
            workspace_ctx.token_generator.load_state({}, {})
            workspace_ctx.vault_data.mappings = {}
            workspace_ctx.vault_data.token_counter = {}
            workspace_ctx.vault_data.file_records = []
            workspace_ctx.vault_data.last_used = now_iso()
            workspace_ctx.persist()

        duration_ms = int((perf_counter() - started) * 1000)
        input_hash = _sha256_text(tokenized_text)
        append_sanitization_report(
            workspace_ctx,
            operation="clipboard_restore",
            file_path=CLIPBOARD_FILE_ID,
            file_ext="clipboard",
            file_hash=input_hash,
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

        return ClipboardRestoreResult(
            tokens_restored=len(active_tokens),
            verification_passed=True,
            restored_text=restored,
        )


def _find_previous_clipboard_record(
    workspace_ctx: WorkspaceContext,
    input_hash: str,
) -> FileRecord | None:
    for record in reversed(workspace_ctx.vault_data.file_records):
        if record.file_path == CLIPBOARD_FILE_ID and record.file_hash_before == input_hash:
            return record
    return None


def _expected_clipboard_tokens(workspace_ctx: WorkspaceContext) -> set[str]:
    for record in reversed(workspace_ctx.vault_data.file_records):
        if record.file_path == CLIPBOARD_FILE_ID:
            return set(record.applied_tokens)
    return set()


def _resolve_locked_model_hash(
    workspace_ctx: WorkspaceContext,
    detection: DetectionEngine,
    model_lock_key: str,
) -> str:
    model_hashes = workspace_ctx.vault_data.model_hashes
    if model_lock_key in model_hashes:
        return model_hashes[model_lock_key]

    legacy_keys = getattr(detection, "legacy_model_lock_keys", ())
    for legacy_key in legacy_keys:
        if legacy_key in model_hashes:
            return model_hashes[legacy_key]
    return ""


def _detect_in_cell(
    detection_engine: DetectionEngine,
    *,
    text: str,
    source_id: str,
    language: str,
):
    try:
        return detection_engine.detect_in_cell(text, source_id, language=language)
    except TypeError:
        # Compatibility for tests using stub engines without language arg.
        return detection_engine.detect_in_cell(text, source_id)


def _create_detection_engine(
    *,
    score_threshold: float,
    detection_mode: str,
    hebrew_backend: str | None,
    hebrew_stanza_model: str | None,
    hebrew_transformer_model: str | None,
) -> DetectionEngine:
    try:
        return DetectionEngine(
            score_threshold=score_threshold,
            detection_mode=detection_mode,
            hebrew_backend=hebrew_backend,
            hebrew_stanza_model=hebrew_stanza_model,
            hebrew_transformer_model=hebrew_transformer_model,
        )
    except TypeError:
        # Compatibility for tests using stub detection engines with legacy signature.
        return DetectionEngine(score_threshold=score_threshold)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pbpaste() -> str:
    proc = subprocess.run(
        ["pbpaste"],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def _pbcopy(text: str) -> None:
    subprocess.run(
        ["pbcopy"],
        check=True,
        input=text,
        text=True,
        capture_output=True,
    )
