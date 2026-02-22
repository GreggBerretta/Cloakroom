"""Presidio AnalyzerEngine wrapper for PII detection."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

from presidio_analyzer import AnalyzerEngine

from cowork_shield.exceptions import DetectionError
from cowork_shield.models import DetectedEntity, EntityType

# Lazy-initialized singleton to avoid loading spaCy on every call
_analyzer: AnalyzerEngine | None = None
_model_hash: str | None = None


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


def _safe_pkg_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _compute_model_hash(analyzer: AnalyzerEngine) -> str:
    payload: dict[str, object] = {
        "presidio_analyzer": _safe_pkg_version("presidio-analyzer"),
        "spacy": _safe_pkg_version("spacy"),
        "en_core_web_lg": _safe_pkg_version("en-core-web-lg"),
    }

    nlp = None
    nlp_engine = getattr(analyzer, "nlp_engine", None)
    if nlp_engine is not None:
        nlp_map = getattr(nlp_engine, "nlp", None)
        if isinstance(nlp_map, dict):
            nlp = nlp_map.get("en")

    if nlp is not None:
        payload["pipeline"] = list(getattr(nlp, "pipe_names", []))
        payload["model_meta"] = getattr(nlp, "meta", {})
        model_path = getattr(nlp, "path", None)
        if model_path:
            model_path = Path(model_path)
            payload["model_path"] = str(model_path)

            for rel_path in ("meta.json", "config.cfg"):
                file_path = model_path / rel_path
                if file_path.exists():
                    payload[f"{rel_path}_sha256"] = hashlib.sha256(
                        file_path.read_bytes()
                    ).hexdigest()

    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _get_model_hash() -> str:
    global _model_hash
    if _model_hash is None:
        analyzer = _get_analyzer()
        _model_hash = _compute_model_hash(analyzer)
    return _model_hash


class DetectionEngine:
    """Wraps Presidio AnalyzerEngine for PII detection.

    Uses AnalyzerEngine.analyze() only. We do NOT use Presidio's
    AnonymizerEngine — token replacement is handled by our own
    tokenizer module for deterministic, reversible behavior.
    """

    DEFAULT_SCORE_THRESHOLD = 0.7
    MODEL_LOCK_KEY = "en_core_web_lg"

    def __init__(self, score_threshold: float = DEFAULT_SCORE_THRESHOLD):
        self._score_threshold = score_threshold

    @property
    def model_lock_key(self) -> str:
        return self.MODEL_LOCK_KEY

    def get_model_hash(self) -> str:
        """Return a deterministic hash of the loaded detection model environment."""
        return _get_model_hash()

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
