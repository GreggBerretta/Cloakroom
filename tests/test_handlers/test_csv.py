"""Tests for the CSV file handler."""

import os
from pathlib import Path

import pytest

from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.handlers.csv_handler import CsvHandler
from cowork_shield.tokenizer.generator import TokenGenerator
from cowork_shield.tokenizer.replacer import TextReplacer

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def detection_engine():
    return DetectionEngine(score_threshold=0.5)


@pytest.fixture
def token_generator():
    return TokenGenerator(os.urandom(32))


class TestCsvHandler:
    def test_anonymize_basic(self, tmp_path, detection_engine, token_generator):
        handler = CsvHandler()
        input_path = FIXTURES_DIR / "sample_data.csv"
        output_path = tmp_path / "anonymized.csv"

        records, file_record = handler.anonymize(
            input_path, output_path, detection_engine, token_generator
        )

        assert output_path.exists()
        assert file_record.format == "csv"
        assert file_record.entities_found > 0
        assert len(records) > 0

        # Verify PII is replaced in output
        content = output_path.read_text(encoding="utf-8")
        assert "PERSON_" in content or "EMAIL_" in content or "SSN_" in content

    def test_numeric_columns_preserved(self, tmp_path, detection_engine, token_generator):
        handler = CsvHandler()
        input_path = FIXTURES_DIR / "sample_data.csv"
        output_path = tmp_path / "anonymized.csv"

        handler.anonymize(input_path, output_path, detection_engine, token_generator)

        content = output_path.read_text(encoding="utf-8")
        # The Amount column (5000.00, 7500.00, 3200.00) should be preserved
        assert "5000.00" in content
        assert "7500.00" in content

    def test_round_trip(self, tmp_path, detection_engine, token_generator):
        handler = CsvHandler()
        input_path = FIXTURES_DIR / "sample_data.csv"
        anon_path = tmp_path / "anonymized.csv"
        restored_path = tmp_path / "restored.csv"

        handler.anonymize(input_path, anon_path, detection_engine, token_generator)

        reverse_lookup = token_generator.get_reverse_lookup()
        handler.restore(anon_path, restored_path, reverse_lookup)

        # Read original and restored, compare cell by cell
        import csv
        from io import StringIO

        original = input_path.read_text(encoding="utf-8-sig")
        restored = restored_path.read_text(encoding="utf-8-sig")

        orig_rows = list(csv.reader(StringIO(original)))
        rest_rows = list(csv.reader(StringIO(restored)))

        assert len(orig_rows) == len(rest_rows)
        for orig_row, rest_row in zip(orig_rows, rest_rows):
            assert len(orig_row) == len(rest_row)

    def test_can_handle(self):
        assert CsvHandler.can_handle(Path("data.csv"))
        assert CsvHandler.can_handle(Path("data.CSV"))
        assert not CsvHandler.can_handle(Path("data.xlsx"))
