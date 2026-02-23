"""Low-cost heuristics to skip obviously non-sensitive cells before NER."""

from __future__ import annotations

from cowork_shield.tokenizer.patterns import ANY_TOKEN_PATTERN


def should_detect_pii(value: str) -> bool:
    """Return True when a cell has enough signal to justify detector invocation."""
    text = (value or "").strip()
    if not text:
        return False

    # Already tokenized content should not be re-detected.
    if ANY_TOKEN_PATTERN.search(text):
        return False

    # Tiny fragments and pure punctuation have near-zero detection value.
    if len(text) < 3:
        return "@" in text
    if not any(char.isalnum() for char in text):
        return False

    return True

