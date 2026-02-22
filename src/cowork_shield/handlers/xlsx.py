"""Excel .xlsx file handler using openpyxl."""

from __future__ import annotations

import shutil
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.exceptions import XLSXContentLossRiskError
from cowork_shield.models import DetectedEntity, FileRecord, ReplacementRecord, now_iso
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

    WARNING: openpyxl can destroy charts, images, and shapes on save.
    This handler blocks by default when those features are present unless
    explicitly overridden.
    """

    def __init__(self, allow_lossy_xlsx: bool = False):
        self._replacer = TextReplacer()
        self._allow_lossy_xlsx = allow_lossy_xlsx

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
        language: str = "auto",
    ) -> tuple[list[ReplacementRecord], FileRecord]:
        # Create backup before any modification
        backup_path = input_path.with_suffix(input_path.suffix + ".backup")
        if not backup_path.exists():
            shutil.copy2(input_path, backup_path)

        wb = load_workbook(str(input_path), data_only=False)
        if self._has_lossy_content(wb) and not self._allow_lossy_xlsx:
            wb.close()
            raise XLSXContentLossRiskError(
                "XLSX contains charts/images that openpyxl may drop. "
                "Re-run with --allow-lossy-xlsx to acknowledge risk."
            )
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

                    entities = _detect_entities(
                        detection_engine,
                        text=value_str,
                        source_id=source_id,
                        language=language,
                    )
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
            applied_tokens=sorted({record.token_text for record in all_records}),
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

    @staticmethod
    def _has_lossy_content(workbook) -> bool:
        for worksheet in workbook.worksheets:
            if getattr(worksheet, "_charts", None):
                if len(worksheet._charts) > 0:
                    return True
            if getattr(worksheet, "_images", None):
                if len(worksheet._images) > 0:
                    return True
        return False


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
