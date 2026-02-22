"""Tests for spreadsheet column selection helpers."""

import pytest

from cowork_shield.exceptions import ColumnSelectionError
from cowork_shield.handlers.column_select import (
    column_letter_to_index,
    index_to_column_letter,
    parse_columns_option,
    resolve_column_selections,
)


class TestColumnSelectionHelpers:
    def test_parse_columns_option(self):
        assert parse_columns_option("A,C,F") == ["A", "C", "F"]
        assert parse_columns_option(" Name, Deal ID ") == ["Name", "Deal ID"]
        assert parse_columns_option("") == []
        assert parse_columns_option(None) == []

    def test_letter_index_round_trip(self):
        assert column_letter_to_index("A") == 0
        assert column_letter_to_index("Z") == 25
        assert column_letter_to_index("AA") == 26
        assert index_to_column_letter(0) == "A"
        assert index_to_column_letter(26) == "AA"

    def test_resolve_by_letter_and_name(self):
        headers = ["Deal ID", "Client Name", "Revenue"]
        selected = resolve_column_selections(
            ["A", "Client Name"],
            headers=headers,
            max_columns=3,
        )
        assert selected[0].token_prefix == "COL_A"
        assert selected[1].token_prefix == "CLIENTNAME"

    def test_unknown_column_raises(self):
        with pytest.raises(ColumnSelectionError):
            resolve_column_selections(
                ["Missing"],
                headers=["A", "B"],
                max_columns=2,
            )
