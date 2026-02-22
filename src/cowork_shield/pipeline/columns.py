"""Column inspection helpers for spreadsheet workflows."""

from __future__ import annotations

from pathlib import Path

from cowork_shield.exceptions import UnsupportedFormatError
from cowork_shield.handlers.column_select import ColumnDescriptor
from cowork_shield.handlers.csv_handler import CsvHandler
from cowork_shield.handlers.xlsx import XlsxHandler


def inspect_columns(file_path: str | Path) -> list[ColumnDescriptor]:
    """Return selectable columns for supported spreadsheet formats."""
    path = Path(file_path).expanduser().resolve()
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return CsvHandler().inspect_columns(path)
    if suffix == ".xlsx":
        return XlsxHandler().inspect_columns(path)

    raise UnsupportedFormatError(suffix)
