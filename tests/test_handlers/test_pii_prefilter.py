"""Tests for cheap PII detection prefilter heuristics."""

from cloakroom.handlers.pii_prefilter import should_detect_pii


def test_prefilter_skips_empty_and_punctuation():
    assert not should_detect_pii("")
    assert not should_detect_pii("   ")
    assert not should_detect_pii("...")


def test_prefilter_skips_existing_tokens():
    assert not should_detect_pii("[PERSON_00001]")
    assert not should_detect_pii("PERSON_00001")


def test_prefilter_allows_realistic_cells():
    assert should_detect_pii("John Smith")
    assert should_detect_pii("john@example.com")
    assert should_detect_pii("(212) 555-1234")

