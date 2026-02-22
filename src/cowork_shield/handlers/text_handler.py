"""Plain text handler for .txt workflows."""

from __future__ import annotations

from pathlib import Path

from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.models import FileRecord, ReplacementRecord, now_iso
from cowork_shield.tokenizer.generator import TokenGenerator
from cowork_shield.tokenizer.replacer import TextReplacer
from cowork_shield.verification.verifier import compute_sha256


class TextHandler:
    """Handles UTF-8 text files as a single analyzable body."""

    def __init__(self):
        self._replacer = TextReplacer()

    @staticmethod
    def can_handle(file_path: Path) -> bool:
        return file_path.suffix.lower() == ".txt"

    def anonymize(
        self,
        input_path: Path,
        output_path: Path,
        detection_engine: DetectionEngine,
        token_generator: TokenGenerator,
        source_file: str = "",
    ) -> tuple[list[ReplacementRecord], FileRecord]:
        text = input_path.read_text(encoding="utf-8", errors="replace")
        entities = detection_engine.detect_in_cell(text, "text:0")
        replaced_text, records = self._replacer.replace_entities(
            text,
            entities,
            token_generator,
            source_file=source_file,
        )
        output_path.write_text(replaced_text, encoding="utf-8")

        file_record = FileRecord(
            file_path=str(input_path),
            file_hash_before=compute_sha256(input_path),
            file_hash_after=compute_sha256(output_path),
            anonymized_path=str(output_path),
            entities_found=len(entities),
            tokens_applied=len(records),
            timestamp=now_iso(),
            format="txt",
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

