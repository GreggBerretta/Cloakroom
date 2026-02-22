"""Presidio AnalyzerEngine wrapper for PII detection."""

from __future__ import annotations

from presidio_analyzer import AnalyzerEngine

from cowork_shield.detection.entity_types import SUPPORTED_PRESIDIO_ENTITIES
from cowork_shield.exceptions import DetectionError
from cowork_shield.models import DetectedEntity, EntityType

# Lazy-initialized singleton to avoid loading spaCy on every call
_analyzer: AnalyzerEngine | None = None


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        try:
            _analyzer = AnalyzerEngine()
        except Exception as e:
            raise DetectionError(
                f"Failed to initialize Presidio. Is spaCy model installed? "
                f"Run: python -m spacy download en_core_web_lg\n{e}"
            ) from e
    return _analyzer


class DetectionEngine:
    """Wraps Presidio AnalyzerEngine for PII detection.

    Uses AnalyzerEngine.analyze() only. We do NOT use Presidio's
    AnonymizerEngine — token replacement is handled by our own
    tokenizer module for deterministic, reversible behavior.
    """

    DEFAULT_SCORE_THRESHOLD = 0.7

    def __init__(self, score_threshold: float = DEFAULT_SCORE_THRESHOLD):
        self._score_threshold = score_threshold

    def detect(self, text: str, language: str = "en") -> list[DetectedEntity]:
        """Detect PII entities in a text string.

        Returns entities sorted by start position (ascending).
        Filters results below the score threshold.
        Resolves overlapping detections by keeping the higher-scored one.
        """
        if not text or not text.strip():
            return []

        analyzer = _get_analyzer()

        try:
            # Pass entities=None to detect all entity types Presidio supports,
            # then filter to our supported types. This avoids warnings about
            # entity types Presidio doesn't have recognizers for (e.g., ORGANIZATION).
            results = analyzer.analyze(
                text=text,
                entities=None,
                language=language,
            )
        except Exception as e:
            raise DetectionError(f"Presidio analysis failed: {e}") from e

        # Filter by threshold
        results = [r for r in results if r.score >= self._score_threshold]

        # Sort by start position
        results.sort(key=lambda r: r.start)

        # Resolve overlapping detections: keep higher-scored one
        resolved = []
        for r in results:
            if resolved and r.start < resolved[-1].end:
                # Overlapping — keep whichever has higher score
                if r.score > resolved[-1].score:
                    resolved[-1] = r
            else:
                resolved.append(r)

        return [
            DetectedEntity(
                entity_type=EntityType(r.entity_type),
                text=text[r.start : r.end],
                start=r.start,
                end=r.end,
                score=r.score,
            )
            for r in resolved
            if EntityType.from_presidio(r.entity_type) is not None
        ]

    def detect_in_cell(
        self, value: str, source_id: str, language: str = "en"
    ) -> list[DetectedEntity]:
        """Detect PII in a single cell value, tagging with source location."""
        entities = self.detect(value, language)
        return [
            DetectedEntity(
                entity_type=e.entity_type,
                text=e.text,
                start=e.start,
                end=e.end,
                score=e.score,
                source_id=source_id,
            )
            for e in entities
        ]
