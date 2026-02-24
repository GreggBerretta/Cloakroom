"""Plain text handler for .txt workflows."""

from __future__ import annotations

from pathlib import Path

from cloakroom.detection.engine import DetectionEngine
from cloakroom.models import DetectedEntity, FileRecord, ReplacementRecord, now_iso
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.tokenizer.replacer import TextReplacer
from cloakroom.verification.verifier import compute_sha256


class TextHandler:
    """Handles UTF-8 text files as a single analyzable body."""

    def __init__(self):
        self._replacer = TextReplacer()

    @staticmethod
    def can_handle(file_path: Path) -> bool:
        return file_path.suffix.lower() in {".txt", ".md"}

    def anonymize(
        self,
        input_path: Path,
        output_path: Path,
        detection_engine: DetectionEngine,
        token_generator: TokenGenerator,
        source_file: str = "",
        language: str = "auto",
        selected_columns: list[str] | None = None,
        detect_pii: bool = True,
    ) -> tuple[list[ReplacementRecord], FileRecord]:
        del selected_columns, detect_pii
        text = input_path.read_text(encoding="utf-8", errors="replace")
        entities = _detect_entities(
            detection_engine,
            text=text,
            source_id="text:0",
            language=language,
        )
        replaced_text, records = self._replacer.replace_entities(
            text,
            entities,
            token_generator,
            source_file=source_file,
        )
        output_path.write_text(replaced_text, encoding="utf-8")
        suffix = input_path.suffix.lower().lstrip(".") or "txt"

        file_record = FileRecord(
            file_path=str(input_path),
            file_hash_before=compute_sha256(input_path),
            file_hash_after=compute_sha256(output_path),
            anonymized_path=str(output_path),
            entities_found=len(entities),
            tokens_applied=len(records),
            timestamp=now_iso(),
            format=suffix,
            applied_tokens=sorted({record.token_text for record in records}),
        )
        return records, file_record

    def restore(
        self,
        input_path: Path,
        output_path: Path,
        reverse_lookup: dict[str, str],
    ) -> None:
        text = input_path.read_text(encoding="utf-8", errors="replace")
        restored = self._replacer.restore_tokens(text, reverse_lookup)
        output_path.write_text(restored, encoding="utf-8")


def _detect_entities(
    detection_engine: DetectionEngine,
    *,
    text: str,
    source_id: str,
    language: str,
) -> list[DetectedEntity]:
    try:
        return detection_engine.detect_in_cell(text, source_id, language=language)
    except TypeError:
        # Compatibility for tests using stub engines without language arg.
        return detection_engine.detect_in_cell(text, source_id)
