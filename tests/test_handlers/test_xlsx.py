"""Tests for the Excel .xlsx file handler."""

import os
from pathlib import Path

import pytest
from openpyxl import load_workbook

from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.handlers.xlsx import XlsxHandler
from cowork_shield.tokenizer.generator import TokenGenerator

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def detection_engine():
    return DetectionEngine(score_threshold=0.5)


@pytest.fixture
def token_generator():
    return TokenGenerator(os.urandom(32))


class TestXlsxHandler:
    def test_anonymize_basic(self, tmp_path, detection_engine, token_generator):
        handler = XlsxHandler()
        input_path = FIXTURES_DIR / "sample_contacts.xlsx"
        output_path = tmp_path / "anonymized.xlsx"

        records, file_record = handler.anonymize(
            input_path, output_path, detection_engine, token_generator
        )

        assert output_path.exists()
        assert file_record.format == "xlsx"
        assert file_record.entities_found > 0
        assert len(records) > 0

    def test_formulas_preserved(self, tmp_path, detection_engine, token_generator):
        handler = XlsxHandler()
        input_path = FIXTURES_DIR / "sample_financial.xlsx"
        output_path = tmp_path / "anonymized.xlsx"

        handler.anonymize(input_path, output_path, detection_engine, token_generator)

        wb = load_workbook(str(output_path), data_only=False)
        ws = wb.active

        # Check that formulas are preserved
        assert ws["F2"].value == "=SUM(B2:E2)"
        assert ws["F3"].value == "=SUM(B3:E3)"
        assert ws["B5"].value == "=SUM(B2:B4)"

        wb.close()

    def test_numeric_cells_untouched(self, tmp_path, detection_engine, token_generator):
        handler = XlsxHandler()
        input_path = FIXTURES_DIR / "sample_financial.xlsx"
        output_path = tmp_path / "anonymized.xlsx"

        handler.anonymize(input_path, output_path, detection_engine, token_generator)

        wb = load_workbook(str(output_path), data_only=False)
        ws = wb.active

        # Numeric cells should be exactly preserved
        assert ws["B2"].value == 50000
        assert ws["C3"].value == 80000

        wb.close()

    def test_round_trip(self, tmp_path, detection_engine, token_generator):
        handler = XlsxHandler()
        input_path = FIXTURES_DIR / "sample_contacts.xlsx"
        anon_path = tmp_path / "anonymized.xlsx"
        restored_path = tmp_path / "restored.xlsx"

        handler.anonymize(input_path, anon_path, detection_engine, token_generator)

        reverse_lookup = token_generator.get_reverse_lookup()
        handler.restore(anon_path, restored_path, reverse_lookup)

        # Compare cell values
        wb_orig = load_workbook(str(input_path), data_only=False)
        wb_rest = load_workbook(str(restored_path), data_only=False)

        for sheet_name in wb_orig.sheetnames:
            ws_orig = wb_orig[sheet_name]
            ws_rest = wb_rest[sheet_name]
            for row_orig, row_rest in zip(ws_orig.iter_rows(), ws_rest.iter_rows()):
                for cell_orig, cell_rest in zip(row_orig, row_rest):
                    if cell_orig.value is not None:
                        assert cell_rest.value == cell_orig.value, (
                            f"Mismatch at {sheet_name}!{cell_orig.coordinate}: "
                            f"expected {cell_orig.value!r}, got {cell_rest.value!r}"
                        )

        wb_orig.close()
        wb_rest.close()

    def test_can_handle(self):
        assert XlsxHandler.can_handle(Path("data.xlsx"))
        assert XlsxHandler.can_handle(Path("data.XLSX"))
        assert not XlsxHandler.can_handle(Path("data.csv"))

    def test_backup_created(self, tmp_path, detection_engine, token_generator):
        handler = XlsxHandler()
        # Copy fixture to tmp so backup can be created next to it
        import shutil
        input_path = tmp_path / "contacts.xlsx"
        shutil.copy2(FIXTURES_DIR / "sample_contacts.xlsx", input_path)
        output_path = tmp_path / "contacts.anonymized.xlsx"

        handler.anonymize(input_path, output_path, detection_engine, token_generator)

        backup_path = input_path.with_suffix(".xlsx.backup")
        assert backup_path.exists()
