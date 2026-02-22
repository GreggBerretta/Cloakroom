"""CSV file handler using Python's csv module."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.models import FileRecord, ReplacementRecord, now_iso
from cowork_shield.tokenizer.generator import TokenGenerator
from cowork_shield.tokenizer.replacer import TextReplacer
from cowork_shield.verification.verifier import compute_sha256


class CsvHandler:
    """Handles .csv files with dialect-preserving anonymization."""

    def __init__(self):
        self._replacer = TextReplacer()

    @staticmethod
    def can_handle(file_path: Path) -> bool:
        return file_path.suffix.lower() == ".csv"

    def anonymize(
        self,
        input_path: Path,
        output_path: Path,
        detection_engine: DetectionEngine,
        token_generator: TokenGenerator,
        source_file: str = "",
    ) -> tuple[list[ReplacementRecord], FileRecord]:
        text = input_path.read_text(encoding="utf-8-sig")

        # Detect dialect
        try:
            dialect = csv.Sniffer().sniff(text[:8192])
        except csv.Error:
            dialect = csv.excel

        reader = csv.reader(StringIO(text), dialect=dialect)
        rows = list(reader)

        all_records: list[ReplacementRecord] = []
        total_entities = 0

        for row_idx, row in enumerate(rows):
            for col_idx, cell_value in enumerate(row):
                if not cell_value or not cell_value.strip():
                    continue

                # Skip numeric-only cells
                try:
                    float(cell_value.replace(",", ""))
                    continue
                except ValueError:
                    pass

                source_id = f"row:{row_idx},col:{col_idx}"
                entities = detection_engine.detect_in_cell(cell_value, source_id)
                total_entities += len(entities)

                if entities:
                    replaced, records = self._replacer.replace_entities(
                        cell_value, entities, token_generator, source_file
                    )
                    rows[row_idx][col_idx] = replaced
                    all_records.extend(records)

        # Write output with same dialect
        output = StringIO()
        writer = csv.writer(output, dialect=dialect)
        writer.writerows(rows)
        # Write with UTF-8 BOM for Excel compatibility
        output_path.write_text(
            "\ufeff" + output.getvalue(), encoding="utf-8"
        )

        file_record = FileRecord(
            file_path=str(input_path),
            file_hash_before=compute_sha256(input_path),
            file_hash_after=compute_sha256(output_path),
            anonymized_path=str(output_path),
            entities_found=total_entities,
            tokens_applied=len(all_records),
            timestamp=now_iso(),
            format="csv",
        )

        return all_records, file_record

    def restore(
        self,
        input_path: Path,
        output_path: Path,
        reverse_lookup: dict[str, str],
    ) -> None:
        text = input_path.read_text(encoding="utf-8-sig")

        try:
            dialect = csv.Sniffer().sniff(text[:8192])
        except csv.Error:
            dialect = csv.excel

        reader = csv.reader(StringIO(text), dialect=dialect)
        rows = list(reader)

        for row_idx, row in enumerate(rows):
            for col_idx, cell_value in enumerate(row):
                if not cell_value:
                    continue
                restored = self._replacer.restore_tokens(cell_value, reverse_lookup)
                if restored != cell_value:
                    rows[row_idx][col_idx] = restored

        output = StringIO()
        writer = csv.writer(output, dialect=dialect)
        writer.writerows(rows)
        output_path.write_text(
            "\ufeff" + output.getvalue(), encoding="utf-8"
        )
