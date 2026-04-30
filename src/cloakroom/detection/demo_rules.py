"""Deterministic dictionary + regex rules for confidential business data.

Demo rules cover types Presidio does not produce: customer names, project
codenames, contract values, pricing terms, strategy phrases, address lines,
and customer IDs. Matches always win over probabilistic NER when they
overlap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable

from cloakroom.models import DetectedEntity, EntityType


@dataclass(frozen=True)
class _CompiledRule:
    pattern: re.Pattern[str]
    entity_type: EntityType
    score: float
    is_dictionary: bool


@dataclass
class DemoRuleSet:
    """Workspace-scoped collection of deterministic detection rules."""

    rules: list[_CompiledRule] = field(default_factory=list)

    def add_dictionary(
        self,
        entity_type: EntityType,
        terms: Iterable[str],
        *,
        score: float = 1.0,
    ) -> None:
        """Add exact-match terms (case-insensitive, whole-token) for a type."""
        cleaned = sorted({term.strip() for term in terms if term and term.strip()}, key=len, reverse=True)
        for term in cleaned:
            escaped = re.escape(term)
            # Use lookarounds rather than \b so multi-word and punctuation-rich
            # terms like "$2.4M" or "Acme Health" still match cleanly.
            pattern = re.compile(rf"(?<!\w){escaped}(?!\w)", flags=re.IGNORECASE)
            self.rules.append(
                _CompiledRule(
                    pattern=pattern,
                    entity_type=entity_type,
                    score=score,
                    is_dictionary=True,
                )
            )

    def add_regex(
        self,
        entity_type: EntityType,
        pattern: str | re.Pattern[str],
        *,
        score: float = 1.0,
        flags: int = 0,
    ) -> None:
        """Add a regex rule for an entity type."""
        if isinstance(pattern, str):
            compiled = re.compile(pattern, flags=flags)
        else:
            compiled = pattern
        self.rules.append(
            _CompiledRule(
                pattern=compiled,
                entity_type=entity_type,
                score=score,
                is_dictionary=False,
            )
        )

    def detect(self, text: str) -> list[DetectedEntity]:
        """Return entities matched by any rule, sorted by start offset."""
        if not text:
            return []

        detected: list[DetectedEntity] = []
        for rule in self.rules:
            for match in rule.pattern.finditer(text):
                start, end = match.span()
                if start >= end:
                    continue
                detected.append(
                    DetectedEntity(
                        entity_type=rule.entity_type,
                        text=text[start:end],
                        start=start,
                        end=end,
                        score=rule.score,
                    )
                )

        return _resolve_overlaps(detected)


def _resolve_overlaps(entities: list[DetectedEntity]) -> list[DetectedEntity]:
    """Sort by start asc, score desc; keep the highest-scoring non-overlap."""
    if not entities:
        return []
    ordered = sorted(entities, key=lambda e: (e.start, -e.score, e.end - e.start))
    resolved: list[DetectedEntity] = []
    for entity in ordered:
        if resolved and entity.start < resolved[-1].end:
            if entity.score > resolved[-1].score or (
                entity.score == resolved[-1].score
                and (entity.end - entity.start) > (resolved[-1].end - resolved[-1].start)
            ):
                resolved[-1] = entity
            continue
        resolved.append(entity)
    return resolved


def build_default_demo_ruleset() -> DemoRuleSet:
    """Return the killer-demo ruleset for the Customer Escalation sample."""
    rs = DemoRuleSet()

    # Customer / organization names
    rs.add_dictionary(EntityType.ORGANIZATION, ["Acme Health"])

    # Strategic project codenames
    rs.add_dictionary(EntityType.PROJECT, ["Project Lantern"])

    # Strategy phrases (multi-word, exact match)
    rs.add_dictionary(
        EntityType.STRATEGY,
        [
            "Q3 churn containment plan",
            "pre-acquisition integration risk",
        ],
    )

    # Address line (full literal address from the demo sample)
    rs.add_dictionary(
        EntityType.ADDRESS_LINE,
        ["15 Farringdon Street, London"],
    )

    # Customer ID format
    rs.add_regex(EntityType.CUSTOMER_ID, r"\bEU-CUST-\d{4,}\b")

    # Contract values: $2.4M, $750K, $1,200,000
    rs.add_regex(
        EntityType.CONTRACT_VALUE,
        r"\$\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*[MK]?\b",
    )

    # Pricing exceptions: "18 percent discount", "12% discount"
    rs.add_regex(
        EntityType.PRICING_TERM,
        r"\b\d+\s*(?:percent|%)\s+discount\b",
        flags=re.IGNORECASE,
    )

    # Renewal dates and other "Month DD, YYYY" forms — keep them as a single
    # DATE token instead of letting Presidio split into ["June 30", "2026"].
    rs.add_regex(
        EntityType.DATE,
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},\s*\d{4}\b",
        flags=re.IGNORECASE,
    )

    return rs
