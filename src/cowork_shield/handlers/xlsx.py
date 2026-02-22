"""Excel .xlsx file handler using openpyxl."""

from __future__ import annotations

import shutil
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.models import FileRecord, ReplacementRecord, now_iso
from cowork_shield.tokenizer.generator import TokenGenerator
from cowork_shield.tokenizer.replacer import TextReplacer
from cowork_shield.verification.verifier import compute_sha256


class XlsxHandler:
    """Handles .xlsx files with cell-level anonymization.

    Design decisions:
    - Load with data_only=False to preserve formulas
    - Skip formula cells (starting with '=') — never modify formulas
    - Skip pure numeric cells (int/float) — no PII in numbers
    - Cell formatting is preserved automatically by openpyxl

    WARNING: openpyxl destroys charts, images, and shapes on save.
    A backup is always created before processing.
    """

    def __init__(self):
        self._replacer = TextReplacer()

    @staticmethod
    def can_handle(file_path: Path) -> bool:
        return file_path.suffix.lower() == ".xlsx"

    def anonymize(
        self,
        input_path: Path,
        output_path: Path,
        detection_engine: DetectionEngine,
        token_generator: TokenGenerator,
        source_file: str = "",
    ) -> tuple[list[ReplacementRecord], FileRecord]:
        # Create backup before any modification
        backup_path = input_path.with_suffix(input_path.suffix + ".backup")
        if not backup_path.exists():
            shutil.copy2(input_path, backup_path)

        wb = load_workbook(str(input_path), data_only=False)
        all_records: list[ReplacementRecord] = []
        total_entities = 0

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue

                    # Skip formula cells
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        continue

                    # Skip pure numeric cells
                    if isinstance(cell.value, (int, float)):
                        continue

                    value_str = str(cell.value)
                    if not value_str.strip():
                        continue

                    source_id = (
                        f"{sheet_name}!{get_column_letter(cell.column)}{cell.row}"
                    )

                    entities = detection_engine.detect_in_cell(value_str, source_id)
                    total_entities += len(entities)

                    if entities:
                        replaced, records = self._replacer.replace_entities(
                            value_str, entities, token_generator, source_file
                        )
                        cell.value = replaced
                        all_records.extend(records)

        wb.save(str(output_path))
        wb.close()

        hash_before = compute_sha256(input_path)
        hash_after = compute_sha256(output_path)

        file_record = FileRecord(
            file_path=str(input_path),
            file_hash_before=hash_before,
            file_hash_after=hash_after,
            anonymized_path=str(output_path),
            entities_found=total_entities,
            tokens_applied=len(all_records),
            timestamp=now_iso(),
            format="xlsx",
        )

        return all_records, file_record

    def restore(
        self,
        input_path: Path,
        output_path: Path,
        reverse_lookup: dict[str, str],
    ) -> None:
        wb = load_workbook(str(input_path), data_only=False)

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue

                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        continue

                    value_str = str(cell.value)
                    restored = self._replacer.restore_tokens(value_str, reverse_lookup)
                    if restored != value_str:
                        cell.value = restored

        wb.save(str(output_path))
        wb.close()
