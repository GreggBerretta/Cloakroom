"""Fast regex-based high-confidence PII extraction.

This module intentionally focuses on patterns where deterministic regex
matching is reliable enough to bypass expensive NER calls.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from cloakroom.models import DetectedEntity, EntityType


EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(
    r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"
)
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
US_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
IL_ID_PATTERN = re.compile(r"\b\d{9}\b")
# Israeli phone: 0XX-XXX-XXXX or +972-XX-XXX-XXXX (mobile and landline)
IL_PHONE_PATTERN = re.compile(
    r"\b(?:\+972[-.\s]?|0)(?:5[0-9]|[2-489])[-.\s]?\d{3}[-.\s]?\d{4}\b"
)
# Israeli bank account: bank-branch-account (2-3 / 2-4 / 6-9 digits)
IL_BANK_ACCOUNT_PATTERN = re.compile(r"\b\d{2,3}-\d{2,4}-\d{6,9}\b")


@dataclass(frozen=True)
class _PatternSpec:
    pattern: re.Pattern[str]
    entity_type: EntityType
    score: float = 1.0


class RegexPreFilter:
    """Extract deterministic PII entities using regex-only matching."""

    def __init__(self) -> None:
        # Order matters: more specific / higher-risk patterns first.
        # IL-specific patterns appear before generic phone so an Israeli mobile
        # like 050-123-4567 is tagged IL_PHONE, not the generic PHONE family.
        self._common_specs = [
            _PatternSpec(CREDIT_CARD_PATTERN, EntityType.CREDIT_CARD),
            _PatternSpec(US_SSN_PATTERN, EntityType.SSN),
            _PatternSpec(EMAIL_PATTERN, EntityType.EMAIL),
            _PatternSpec(IL_PHONE_PATTERN, EntityType.IL_PHONE),
            _PatternSpec(IL_BANK_ACCOUNT_PATTERN, EntityType.IL_BANK_ACCOUNT),
            _PatternSpec(PHONE_PATTERN, EntityType.PHONE),
        ]
        self._hebrew_extra_specs = [
            _PatternSpec(IL_ID_PATTERN, EntityType.TEUDAT_ZEHUT),
        ]

    def extract_entities(self, text: str, *, language: str) -> list[DetectedEntity]:
        if not text or not text.strip():
            return []

        # In Hebrew text, IL-specific patterns (e.g. 9-digit Teudat Zehut) must
        # match before the generic phone pattern, otherwise a bare ID like
        # "312345674" gets falsely tagged as PHONE.
        if language == "he":
            specs = list(self._hebrew_extra_specs) + list(self._common_specs)
        else:
            specs = list(self._common_specs)

        detected: list[DetectedEntity] = []
        taken_spans: list[tuple[int, int]] = []

        for spec in specs:
            for match in spec.pattern.finditer(text):
                start, end = match.span()
                if start >= end:
                    continue
                if _overlaps_any(start, end, taken_spans):
                    continue

                candidate = match.group(0)
                if not self._is_valid_candidate(candidate, spec.entity_type):
                    continue

                taken_spans.append((start, end))
                detected.append(
                    DetectedEntity(
                        entity_type=spec.entity_type,
                        text=candidate,
                        start=start,
                        end=end,
                        score=spec.score,
                    )
                )

        detected.sort(key=lambda item: item.start)
        return detected

    @staticmethod
    def _is_valid_candidate(candidate: str, entity_type: EntityType) -> bool:
        if entity_type is EntityType.PHONE:
            digits = sum(1 for char in candidate if char.isdigit())
            return digits >= 7
        if entity_type is EntityType.CREDIT_CARD:
            digits = "".join(char for char in candidate if char.isdigit())
            if len(digits) != 16:
                return False
            return _passes_luhn(digits)
        return True


def _overlaps_any(start: int, end: int, spans: Iterable[tuple[int, int]]) -> bool:
    for existing_start, existing_end in spans:
        if start < existing_end and end > existing_start:
            return True
    return False


def _passes_luhn(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for idx, char in enumerate(digits):
        value = int(char)
        if idx % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0
