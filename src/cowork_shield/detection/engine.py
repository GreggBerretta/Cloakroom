"""Presidio AnalyzerEngine wrapper for PII detection."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path

from langdetect import LangDetectException, detect as detect_language_code
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from cowork_shield.exceptions import DetectionError
from cowork_shield.models import DetectedEntity, EntityType

SUPPORTED_LANGUAGES = ("en", "he")
LANGUAGE_CHOICES = ("auto", "en", "he")
ENGLISH_MODEL_NAME = "en_core_web_lg"
HEBREW_MODEL_PRIMARY = "he_core_news_sm"
HEBREW_MODEL_FALLBACK = "xx_ent_wiki_sm"

# Lazy-initialized singleton to avoid loading spaCy on every call
_analyzer: AnalyzerEngine | None = None
_model_hash: str | None = None
_loaded_models: dict[str, str] = {"en": ENGLISH_MODEL_NAME, "he": HEBREW_MODEL_PRIMARY}


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        try:
            if not _model_is_installed(ENGLISH_MODEL_NAME):
                raise DetectionError(
                    "English model is not installed. Run: python -m spacy download en_core_web_lg"
                )

            hebrew_model = _resolve_hebrew_model()
            _analyzer = _create_analyzer(
                english_model=ENGLISH_MODEL_NAME,
                hebrew_model=hebrew_model,
            )
            _loaded_models["en"] = ENGLISH_MODEL_NAME
            _loaded_models["he"] = hebrew_model
        except DetectionError:
            raise
        except Exception as e:
            raise DetectionError(
                "Failed to initialize Presidio multi-language engine.\n"
                "Install required models:\n"
                "  python -m spacy download en_core_web_lg\n"
                "  python -m spacy download he_core_news_sm\n"
                "If he_core_news_sm is unavailable in your spaCy build, install:\n"
                "  python -m spacy download xx_ent_wiki_sm\n"
                f"{e}"
            ) from e
    return _analyzer


def _model_is_installed(model_name: str) -> bool:
    return importlib.util.find_spec(model_name) is not None


def _resolve_hebrew_model() -> str:
    if _model_is_installed(HEBREW_MODEL_PRIMARY):
        return HEBREW_MODEL_PRIMARY
    if _model_is_installed(HEBREW_MODEL_FALLBACK):
        return HEBREW_MODEL_FALLBACK
    raise DetectionError(
        "Hebrew model is not installed. Run one of:\n"
        "  python -m spacy download he_core_news_sm\n"
        "  python -m spacy download xx_ent_wiki_sm"
    )


def _create_analyzer(*, english_model: str, hebrew_model: str) -> AnalyzerEngine:
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": "en", "model_name": english_model},
                {"lang_code": "he", "model_name": hebrew_model},
            ],
        }
    )
    nlp_engine = provider.create_engine()
    return AnalyzerEngine(
        nlp_engine=nlp_engine,
        supported_languages=list(SUPPORTED_LANGUAGES),
    )


def _safe_pkg_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _safe_model_config_hash(model_path: Path, rel_path: str) -> str:
    file_path = model_path / rel_path
    if not file_path.exists():
        return ""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _compute_model_hash(analyzer: AnalyzerEngine) -> str:
    payload: dict[str, object] = {
        "presidio_analyzer": _safe_pkg_version("presidio-analyzer"),
        "spacy": _safe_pkg_version("spacy"),
        "langdetect": _safe_pkg_version("langdetect"),
        "en_core_web_lg": _safe_pkg_version("en-core-web-lg"),
        "he_core_news_sm": _safe_pkg_version("he-core-news-sm"),
        "xx_ent_wiki_sm": _safe_pkg_version("xx-ent-wiki-sm"),
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "loaded_models": dict(_loaded_models),
    }

    nlp_engine = getattr(analyzer, "nlp_engine", None)
    nlp_map = getattr(nlp_engine, "nlp", None) if nlp_engine is not None else None
    if isinstance(nlp_map, dict):
        for lang in SUPPORTED_LANGUAGES:
            nlp = nlp_map.get(lang)
            if nlp is None:
                continue
            lang_payload: dict[str, object] = {
                "pipeline": list(getattr(nlp, "pipe_names", [])),
                "model_meta": getattr(nlp, "meta", {}),
            }
            model_path = getattr(nlp, "path", None)
            if model_path:
                model_path = Path(model_path)
                lang_payload["model_path"] = str(model_path)
                lang_payload["meta_json_sha256"] = _safe_model_config_hash(model_path, "meta.json")
                lang_payload["config_cfg_sha256"] = _safe_model_config_hash(model_path, "config.cfg")
            payload[f"model:{lang}"] = lang_payload

    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _get_model_hash() -> str:
    global _model_hash
    if _model_hash is None:
        analyzer = _get_analyzer()
        _model_hash = _compute_model_hash(analyzer)
    return _model_hash


def _normalize_language(language: str) -> str:
    value = (language or "auto").strip().lower()
    if value not in LANGUAGE_CHOICES:
        raise DetectionError(
            f"Unsupported language '{language}'. Expected one of: {', '.join(LANGUAGE_CHOICES)}"
        )
    return value


def _auto_detect_language(text: str) -> str:
    if not text or not text.strip():
        return "en"
    try:
        detected = detect_language_code(text).lower()
    except LangDetectException:
        return "en"
    except Exception:
        return "en"

    if detected in ("he", "iw"):
        return "he"
    return "en"


class DetectionEngine:
    """Wraps Presidio AnalyzerEngine for PII detection.

    Uses AnalyzerEngine.analyze() only. We do NOT use Presidio's
    AnonymizerEngine -- token replacement is handled by our own
    tokenizer module for deterministic, reversible behavior.
    """

    DEFAULT_SCORE_THRESHOLD = 0.7
    MODEL_LOCK_KEY = "spacy_multilang_en_he"
    LEGACY_MODEL_LOCK_KEYS = ("en_core_web_lg",)

    def __init__(
        self,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        default_language: str = "auto",
    ):
        self._score_threshold = score_threshold
        self._default_language = _normalize_language(default_language)

    @property
    def model_lock_key(self) -> str:
        return self.MODEL_LOCK_KEY

    @property
    def legacy_model_lock_keys(self) -> tuple[str, ...]:
        return self.LEGACY_MODEL_LOCK_KEYS

    def get_model_hash(self) -> str:
        """Return a deterministic hash of the loaded detection model environment."""
        return _get_model_hash()

    def resolve_language(self, text: str, language: str | None = None) -> str:
        requested = self._default_language if language is None else _normalize_language(language)
        if requested == "auto":
            return _auto_detect_language(text)
        return requested

    def detect(self, text: str, language: str | None = None) -> list[DetectedEntity]:
        """Detect PII entities in a text string.

        Returns entities sorted by start position (ascending).
        Filters results below the score threshold.
        Resolves overlapping detections by keeping the higher-scored one.
        """
        if not text or not text.strip():
            return []

        analyzer = _get_analyzer()
        resolved_language = self.resolve_language(text, language)

        try:
            # Pass entities=None to detect all entity types Presidio supports,
            # then filter to our supported types. This avoids warnings about
            # entity types Presidio doesn't have recognizers for (e.g., ORGANIZATION).
            results = analyzer.analyze(
                text=text,
                entities=None,
                language=resolved_language,
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
                # Overlapping -- keep whichever has higher score
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
        self,
        value: str,
        source_id: str,
        language: str | None = None,
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
