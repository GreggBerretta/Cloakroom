"""Tests for spreadsheet column inspection pipeline."""

from pathlib import Path

import pytest

from cowork_shield.exceptions import UnsupportedFormatError
from cowork_shield.pipeline.columns import inspect_columns

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_inspect_columns_csv():
    columns = inspect_columns(FIXTURES_DIR / "sample_data.csv")
    assert len(columns) == 5
    assert columns[0].letter == "A"
    assert columns[0].name == "Name"


def test_inspect_columns_xlsx():
    columns = inspect_columns(FIXTURES_DIR / "sample_contacts.xlsx")
    assert columns
    assert columns[0].letter == "A"


def test_inspect_columns_rejects_non_spreadsheet(tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("hello", encoding="utf-8")
    with pytest.raises(UnsupportedFormatError):
        inspect_columns(text_file)
