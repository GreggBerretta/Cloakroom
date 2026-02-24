"""CSV file handler using Python's csv module."""

from __future__ import annotations

from collections import defaultdict
import csv
from io import StringIO
from pathlib import Path

from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.handlers.column_select import (
    ColumnDescriptor,
    describe_columns,
    infer_data_type,
    resolve_column_selections,
)
from cowork_shield.handlers.pii_prefilter import should_detect_pii
from cowork_shield.models import DetectedEntity, EntityType, FileRecord, ReplacementRecord, now_iso
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
        language: str = "auto",
        selected_columns: list[str] | None = None,
        detect_pii: bool = True,
    ) -> tuple[list[ReplacementRecord], FileRecord]:
        text = input_path.read_text(encoding="utf-8-sig")

        # Detect dialect
        try:
            dialect = csv.Sniffer().sniff(text[:8192])
        except csv.Error:
            dialect = csv.excel

        reader = csv.reader(StringIO(text), dialect=dialect)
        rows = list(reader)
        max_columns = max((len(row) for row in rows), default=0)
        headers = rows[0] if rows else []
        selected_map = resolve_column_selections(
            selected_columns or [],
            headers=headers,
            max_columns=max_columns,
        )

        all_records: list[ReplacementRecord] = []
        total_entities = 0

        for row_idx, row in enumerate(rows):
            pii_candidates: list[tuple[int, str]] = []
            for col_idx, cell_value in enumerate(row):
                if not cell_value or not cell_value.strip():
                    continue

                selection = selected_map.get(col_idx)
                if selection is not None:
                    # Treat first row as header for column mode and preserve names.
                    if row_idx == 0:
                        continue
                    source_id = f"row:{row_idx},col:{col_idx}"
                    token = token_generator.get_or_create_column_token(
                        cell_value,
                        selection.token_prefix,
                        source_file=source_file,
                    )
                    rows[row_idx][col_idx] = token.token_text
                    all_records.append(
                        ReplacementRecord(
                            location=source_id,
                            original_value=cell_value,
                            token_text=token.token_text,
                            entity_type=EntityType.COLUMN,
                        )
                    )
                    total_entities += 1
                    continue

                if not detect_pii:
                    continue

                if not should_detect_pii(cell_value):
                    continue

                # Skip numeric-only cells
                try:
                    float(cell_value.replace(",", ""))
                    continue
                except ValueError:
                    pii_candidates.append((col_idx, cell_value))

            if not detect_pii or not pii_candidates:
                continue

            detected_by_col = _detect_entities_for_csv_row(
                detection_engine,
                row_idx=row_idx,
                candidates=pii_candidates,
                language=language,
            )

            for col_idx, entities in detected_by_col.items():
                total_entities += len(entities)
                if not entities:
                    continue
                source_value = rows[row_idx][col_idx]
                replaced, records = self._replacer.replace_entities(
                    source_value,
                    entities,
                    token_generator,
                    source_file,
                )
                rows[row_idx][col_idx] = replaced
                all_records.extend(records)

        # Write output with same dialect
        output = StringIO()
        writer = csv.writer(output, dialect=dialect)
        writer.writerows(rows)
        # Write with UTF-8 BOM for Excel compatibility
        output_path.write_text("\ufeff" + output.getvalue(), encoding="utf-8")

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

    def inspect_columns(self, input_path: Path) -> list[ColumnDescriptor]:
        """Return available columns in a CSV file."""
        text = input_path.read_text(encoding="utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(text[:8192])
        except csv.Error:
            dialect = csv.excel

        reader = csv.reader(StringIO(text), dialect=dialect)
        rows = list(reader)
        max_columns = max((len(row) for row in rows), default=0)
        headers = rows[0] if rows else []
        samples = _collect_csv_samples(rows, max_columns)
        data_types = {
            idx: infer_data_type(values)
            for idx, values in samples.items()
        }
        return describe_columns(
            headers,
            max_columns,
            sample_values=samples,
            data_types=data_types,
        )

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
                if "[" not in cell_value and "_" not in cell_value:
                    continue
                restored = self._replacer.restore_tokens(cell_value, reverse_lookup)
                if restored != cell_value:
                    rows[row_idx][col_idx] = restored

        output = StringIO()
        writer = csv.writer(output, dialect=dialect)
        writer.writerows(rows)
        output_path.write_text("\ufeff" + output.getvalue(), encoding="utf-8")


def _collect_csv_samples(rows: list[list[str]], max_columns: int) -> dict[int, list[str]]:
    samples: dict[int, list[str]] = {idx: [] for idx in range(max_columns)}
    for row in rows[1:]:
        for idx in range(max_columns):
            if len(samples[idx]) >= 3:
                continue
            if idx >= len(row):
                continue
            value = (row[idx] or "").strip()
            if value:
                samples[idx].append(value[:40])
        if all(len(values) >= 3 for values in samples.values()):
            break
    return samples


def _detect_entities_for_csv_row(
    detection_engine: DetectionEngine,
    *,
    row_idx: int,
    candidates: list[tuple[int, str]],
    language: str,
) -> dict[int, list[DetectedEntity]]:
    delimiter = "\u241f"
    text_parts = [value for _, value in candidates]
    merged = delimiter.join(text_parts)
    source_id = f"row:{row_idx}"

    try:
        merged_entities = detection_engine.detect_in_cell(merged, source_id, language=language)
    except TypeError:
        merged_entities = detection_engine.detect_in_cell(merged, source_id)

    segments: list[tuple[int, int, int, str]] = []
    cursor = 0
    for col_idx, value in candidates:
        start = cursor
        end = start + len(value)
        segments.append((col_idx, start, end, value))
        cursor = end + len(delimiter)

    entities_by_col: dict[int, list[DetectedEntity]] = defaultdict(list)
    for entity in merged_entities:
        for col_idx, start, end, value in segments:
            if entity.start < start or entity.end > end:
                continue
            local_start = entity.start - start
            local_end = entity.end - start
            if local_start < 0 or local_end > len(value):
                continue
            entities_by_col[col_idx].append(
                DetectedEntity(
                    entity_type=entity.entity_type,
                    text=value[local_start:local_end],
                    start=local_start,
                    end=local_end,
                    score=entity.score,
                    source_id=f"row:{row_idx},col:{col_idx}",
                )
            )
            break

    for col_idx in entities_by_col:
        entities_by_col[col_idx].sort(key=lambda item: item.start)
    return entities_by_col
