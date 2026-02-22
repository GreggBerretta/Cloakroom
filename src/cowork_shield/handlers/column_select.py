"""Helpers for spreadsheet column inspection and selection."""

from __future__ import annotations

from dataclasses import dataclass
import re

from cowork_shield.exceptions import ColumnSelectionError


@dataclass(frozen=True)
class ColumnDescriptor:
    """Describes a selectable spreadsheet column."""

    index: int
    letter: str
    name: str
    data_type: str = "text"
    sample_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class ColumnSelection:
    """Resolved user selection for a column."""

    index: int
    letter: str
    name: str
    token_prefix: str
    selected_by_name: bool


def parse_columns_option(columns: str | None) -> list[str]:
    """Parse comma-separated column identifiers."""
    if columns is None:
        return []
    return [part.strip() for part in columns.split(",") if part.strip()]


def column_letter_to_index(letter: str) -> int:
    """Convert Excel-style column letters (A, C, AA) to zero-based index."""
    normalized = (letter or "").strip().upper()
    if not re.fullmatch(r"[A-Z]+", normalized):
        raise ColumnSelectionError(f"Invalid column letter: {letter!r}")

    index = 0
    for char in normalized:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def index_to_column_letter(index: int) -> str:
    """Convert zero-based column index to Excel-style letter."""
    if index < 0:
        raise ColumnSelectionError(f"Column index must be >= 0, got {index}")

    value = index + 1
    letters: list[str] = []
    while value > 0:
        value, rem = divmod(value - 1, 26)
        letters.append(chr(ord("A") + rem))
    return "".join(reversed(letters))


def describe_columns(
    headers: list[str],
    max_columns: int,
    sample_values: dict[int, list[str]] | None = None,
    data_types: dict[int, str] | None = None,
) -> list[ColumnDescriptor]:
    """Build a column catalog from header row and max column count."""
    sample_values = sample_values or {}
    data_types = data_types or {}
    descriptors: list[ColumnDescriptor] = []
    for idx in range(max_columns):
        header = headers[idx] if idx < len(headers) else ""
        header_clean = str(header).strip()
        name = header_clean or f"Column {index_to_column_letter(idx)}"
        samples = tuple(sample_values.get(idx, []))
        descriptors.append(
            ColumnDescriptor(
                index=idx,
                letter=index_to_column_letter(idx),
                name=name,
                data_type=data_types.get(idx, infer_data_type(list(samples))),
                sample_values=samples,
            )
        )
    return descriptors


def infer_data_type(samples: list[str]) -> str:
    """Infer a lightweight display data type from sampled values."""
    normalized = [sample.strip() for sample in samples if sample and sample.strip()]
    if not normalized:
        return "unknown"

    def _is_number(value: str) -> bool:
        cleaned = value.replace(",", "").replace("$", "").replace("%", "")
        return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned))

    def _is_date(value: str) -> bool:
        return bool(
            re.fullmatch(
                r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?",
                value,
            )
        )

    if all(_is_number(value) for value in normalized):
        return "number"
    if all(_is_date(value) for value in normalized):
        return "date"

    has_number = any(_is_number(value) for value in normalized)
    has_date = any(_is_date(value) for value in normalized)
    if has_number or has_date:
        return "mixed"
    return "text"


def resolve_column_selections(
    identifiers: list[str],
    headers: list[str],
    max_columns: int,
) -> dict[int, ColumnSelection]:
    """Resolve user-specified column identifiers to concrete columns."""
    if not identifiers:
        return {}

    if max_columns <= 0:
        raise ColumnSelectionError("No columns were found in the file.")

    descriptors = describe_columns(headers, max_columns)
    by_letter = {descriptor.letter.upper(): descriptor for descriptor in descriptors}
    by_name = {descriptor.name.lower(): descriptor for descriptor in descriptors}

    selections: dict[int, ColumnSelection] = {}
    missing: list[str] = []

    for raw in identifiers:
        identifier = raw.strip()
        if not identifier:
            continue

        descriptor: ColumnDescriptor | None = None
        selected_by_name = False
        if re.fullmatch(r"[A-Za-z]+", identifier):
            descriptor = by_letter.get(identifier.upper())
        if descriptor is None:
            descriptor = by_name.get(identifier.lower())
            selected_by_name = descriptor is not None

        if descriptor is None:
            missing.append(identifier)
            continue

        token_prefix = _token_prefix_for_selection(
            descriptor,
            selected_by_name=selected_by_name,
        )
        selections[descriptor.index] = ColumnSelection(
            index=descriptor.index,
            letter=descriptor.letter,
            name=descriptor.name,
            token_prefix=token_prefix,
            selected_by_name=selected_by_name,
        )

    if missing:
        available = ", ".join(
            f"{descriptor.letter}:{descriptor.name}" for descriptor in descriptors
        )
        raise ColumnSelectionError(
            "Unknown column(s): "
            f"{', '.join(missing)}. Available columns: {available}"
        )

    return selections


def _token_prefix_for_selection(
    descriptor: ColumnDescriptor,
    *,
    selected_by_name: bool,
) -> str:
    # Letter-based selectors preserve explicit column intent.
    if not selected_by_name:
        return f"COL_{descriptor.letter}"

    cleaned = re.sub(r"[^A-Za-z0-9]", "", descriptor.name.upper())
    if not cleaned:
        return f"COL_{descriptor.letter}"
    if cleaned[0].isdigit():
        cleaned = f"C{cleaned}"
    return cleaned[:64]
