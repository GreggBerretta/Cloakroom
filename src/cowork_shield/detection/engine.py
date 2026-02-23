"""Presidio AnalyzerEngine wrapper for PII detection."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import re
from typing import Any

from langdetect import LangDetectException, detect as detect_language_code
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import (
    NerModelConfiguration,
    NlpEngineProvider,
    StanzaNlpEngine,
    TransformersNlpEngine,
)

from cowork_shield.exceptions import DetectionError
from cowork_shield.models import DetectedEntity, EntityType

SUPPORTED_LANGUAGES = ("en", "he")
LANGUAGE_CHOICES = ("auto", "en", "he")
HEBREW_BACKEND_CHOICES = ("auto", "spacy", "stanza", "transformers")

ENGLISH_MODEL_NAME = "en_core_web_lg"
HEBREW_MODEL_PRIMARY = "he_core_news_sm"
HEBREW_MODEL_FALLBACK = "xx_ent_wiki_sm"

DEFAULT_HEBREW_BACKEND = "auto"
DEFAULT_HEBREW_STANZA_MODEL = "he"
DEFAULT_HEBREW_TRANSFORMER_MODEL = "CordwainerSmith/GolemPII-v1"

HEBREW_BACKEND_ENV = "CWS_HEBREW_NLP_ENGINE"
HEBREW_STANZA_MODEL_ENV = "CWS_HEBREW_STANZA_MODEL"
HEBREW_TRANSFORMER_MODEL_ENV = "CWS_HEBREW_TRANSFORMER_MODEL"
HEBREW_TRANSFORMER_SPACY_MODEL_ENV = "CWS_HEBREW_TRANSFORMER_SPACY_MODEL"

HEBREW_ENTITY_MAPPING = {
    "PER": "PERSON",
    "PERSON": "PERSON",
    "ORG": "ORGANIZATION",
    "ORGANIZATION": "ORGANIZATION",
    "LOC": "LOCATION",
    "LOCATION": "LOCATION",
    "GPE": "LOCATION",
    "EMAIL": "EMAIL_ADDRESS",
    "E_MAIL": "EMAIL_ADDRESS",
    "PHONE": "PHONE_NUMBER",
    "PHONE_NUMBER": "PHONE_NUMBER",
    "TEL": "PHONE_NUMBER",
    "DATE": "DATE_TIME",
    "DATE_TIME": "DATE_TIME",
    "TIME": "DATE_TIME",
    "ID": "US_SSN",
    "NATIONAL_ID": "US_SSN",
    "TEUDAT_ZEHUT": "US_SSN",
    "CREDIT_CARD": "CREDIT_CARD",
    "CARD": "CREDIT_CARD",
    "IP": "IP_ADDRESS",
    "IP_ADDRESS": "IP_ADDRESS",
    "URL": "URL",
}

_english_analyzer: AnalyzerEngine | None = None
_hebrew_analyzer_cache: dict[str, AnalyzerEngine] = {}
_hebrew_profile_cache: dict[str, dict[str, str]] = {}
_HEBREW_SCRIPT_RE = re.compile(r"[\u0590-\u05FF]")

_TARGET_PRESIDIO_ENTITIES = tuple(
    entity_type.value
    for entity_type in EntityType
    if entity_type is not EntityType.COLUMN
)


def _safe_pkg_version(package_name: str) -> str:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _model_is_installed(model_name: str) -> bool:
    return importlib.util.find_spec(model_name) is not None


def _safe_model_config_hash(model_path: Path, rel_path: str) -> str:
    file_path = model_path / rel_path
    if not file_path.exists():
        return ""
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _normalize_language(language: str) -> str:
    value = (language or "auto").strip().lower()
    if value not in LANGUAGE_CHOICES:
        raise DetectionError(
            f"Unsupported language '{language}'. Expected one of: {', '.join(LANGUAGE_CHOICES)}"
        )
    return value


def _normalize_hebrew_backend(backend: str) -> str:
    value = (backend or DEFAULT_HEBREW_BACKEND).strip().lower()
    if value not in HEBREW_BACKEND_CHOICES:
        raise DetectionError(
            "Unsupported Hebrew backend "
            f"'{backend}'. Expected one of: {', '.join(HEBREW_BACKEND_CHOICES)}"
        )
    return value


def _resolve_hebrew_backend(requested_backend: str) -> str:
    backend = _normalize_hebrew_backend(requested_backend)
    if backend != "auto":
        return backend
    # Keep default behavior stable unless explicitly configured.
    return "spacy"


def _auto_detect_language(text: str) -> str:
    if not text or not text.strip():
        return "en"
    # Fast path: if any Hebrew script characters are present, force Hebrew.
    # This avoids expensive per-cell language detection for large spreadsheets.
    if _HEBREW_SCRIPT_RE.search(text):
        return "he"

    # Fast path for common spreadsheet text (ASCII): default to English.
    if text.isascii():
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


def _resolve_hebrew_spacy_model() -> str:
    if _model_is_installed(HEBREW_MODEL_PRIMARY):
        return HEBREW_MODEL_PRIMARY
    if _model_is_installed(HEBREW_MODEL_FALLBACK):
        return HEBREW_MODEL_FALLBACK
    raise DetectionError(
        "Hebrew spaCy model is not installed. Run one of:\n"
        "  python -m spacy download he_core_news_sm\n"
        "  python -m spacy download xx_ent_wiki_sm"
    )


def _resolve_hebrew_transformer_spacy_model() -> str:
    preferred = os.getenv(HEBREW_TRANSFORMER_SPACY_MODEL_ENV, "").strip()
    if preferred:
        if _model_is_installed(preferred):
            return preferred
        raise DetectionError(
            f"{HEBREW_TRANSFORMER_SPACY_MODEL_ENV}={preferred} is not installed as a spaCy model."
        )

    for candidate in (HEBREW_MODEL_PRIMARY, HEBREW_MODEL_FALLBACK, ENGLISH_MODEL_NAME):
        if _model_is_installed(candidate):
            return candidate

    raise DetectionError(
        "No tokenizer model is available for Hebrew transformers backend.\n"
        "Install one of:\n"
        "  python -m spacy download he_core_news_sm\n"
        "  python -m spacy download xx_ent_wiki_sm\n"
        "  python -m spacy download en_core_web_lg"
    )


def _hebrew_ner_model_configuration() -> NerModelConfiguration:
    return NerModelConfiguration.from_dict(
        {
            "model_to_presidio_entity_mapping": HEBREW_ENTITY_MAPPING,
            "labels_to_ignore": ["MISC"],
        }
    )


def _create_english_analyzer() -> AnalyzerEngine:
    if not _model_is_installed(ENGLISH_MODEL_NAME):
        raise DetectionError(
            "English model is not installed. Run: python -m spacy download en_core_web_lg"
        )

    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": ENGLISH_MODEL_NAME}],
        }
    )
    nlp_engine = provider.create_engine()
    return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])


def _create_hebrew_spacy_analyzer() -> tuple[AnalyzerEngine, dict[str, str]]:
    hebrew_model = _resolve_hebrew_spacy_model()
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "he", "model_name": hebrew_model}],
            "ner_model_configuration": {
                "model_to_presidio_entity_mapping": HEBREW_ENTITY_MAPPING,
                "labels_to_ignore": ["MISC"],
            },
        }
    )
    nlp_engine = provider.create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["he"])
    return analyzer, {"backend": "spacy", "model_name": hebrew_model}


def _create_hebrew_stanza_analyzer(stanza_model: str) -> tuple[AnalyzerEngine, dict[str, str]]:
    if not _module_available("stanza"):
        raise DetectionError(
            "Stanza backend requested but stanza is not installed.\n"
            "Run: uv pip install stanza"
        )

    nlp_engine = StanzaNlpEngine(
        models=[{"lang_code": "he", "model_name": stanza_model}],
        ner_model_configuration=_hebrew_ner_model_configuration(),
        download_if_missing=False,
    )
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["he"])
    return analyzer, {"backend": "stanza", "model_name": stanza_model}


def _create_hebrew_transformers_analyzer(
    transformer_model: str,
) -> tuple[AnalyzerEngine, dict[str, str]]:
    if not _module_available("transformers") or not _module_available("spacy_huggingface_pipelines"):
        raise DetectionError(
            "Transformers backend requested but dependencies are missing.\n"
            "Run: uv pip install transformers spacy-huggingface-pipelines"
        )

    tokenizer_model = _resolve_hebrew_transformer_spacy_model()
    nlp_engine = TransformersNlpEngine(
        models=[
            {
                "lang_code": "he",
                "model_name": {
                    "spacy": tokenizer_model,
                    "transformers": transformer_model,
                },
            }
        ],
        ner_model_configuration=_hebrew_ner_model_configuration(),
    )
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["he"])
    return analyzer, {
        "backend": "transformers",
        "model_name": transformer_model,
        "tokenizer_model": tokenizer_model,
    }


def _get_english_analyzer() -> AnalyzerEngine:
    global _english_analyzer
    if _english_analyzer is None:
        _english_analyzer = _create_english_analyzer()
    return _english_analyzer


def _get_hebrew_analyzer(
    backend: str,
    *,
    stanza_model: str,
    transformer_model: str,
) -> tuple[AnalyzerEngine, dict[str, str]]:
    cache_key = f"{backend}|{stanza_model}|{transformer_model}"
    cached = _hebrew_analyzer_cache.get(cache_key)
    if cached is not None:
        return cached, _hebrew_profile_cache[cache_key]

    if backend == "spacy":
        analyzer, profile = _create_hebrew_spacy_analyzer()
    elif backend == "stanza":
        analyzer, profile = _create_hebrew_stanza_analyzer(stanza_model)
    elif backend == "transformers":
        analyzer, profile = _create_hebrew_transformers_analyzer(transformer_model)
    else:
        raise DetectionError(f"Unsupported Hebrew backend: {backend}")

    _hebrew_analyzer_cache[cache_key] = analyzer
    _hebrew_profile_cache[cache_key] = profile
    return analyzer, profile


def _append_nlp_payload(
    payload: dict[str, Any],
    analyzer: AnalyzerEngine,
    *,
    lang: str,
    key_prefix: str,
) -> None:
    nlp_engine = getattr(analyzer, "nlp_engine", None)
    nlp_map = getattr(nlp_engine, "nlp", None) if nlp_engine is not None else None
    if not isinstance(nlp_map, dict):
        return

    nlp = nlp_map.get(lang)
    if nlp is None:
        return

    entry: dict[str, Any] = {
        "pipeline": list(getattr(nlp, "pipe_names", [])),
        "model_meta": getattr(nlp, "meta", {}),
    }
    model_path = getattr(nlp, "path", None)
    if model_path:
        model_path = Path(model_path)
        entry["model_path"] = str(model_path)
        entry["meta_json_sha256"] = _safe_model_config_hash(model_path, "meta.json")
        entry["config_cfg_sha256"] = _safe_model_config_hash(model_path, "config.cfg")

    payload[key_prefix] = entry


def _compute_model_hash(
    english_analyzer: AnalyzerEngine,
    hebrew_analyzer: AnalyzerEngine,
    *,
    hebrew_profile: dict[str, str],
) -> str:
    payload: dict[str, Any] = {
        "presidio_analyzer": _safe_pkg_version("presidio-analyzer"),
        "spacy": _safe_pkg_version("spacy"),
        "langdetect": _safe_pkg_version("langdetect"),
        "stanza": _safe_pkg_version("stanza"),
        "transformers": _safe_pkg_version("transformers"),
        "spacy_huggingface_pipelines": _safe_pkg_version("spacy-huggingface-pipelines"),
        "en_core_web_lg": _safe_pkg_version("en-core-web-lg"),
        "he_core_news_sm": _safe_pkg_version("he-core-news-sm"),
        "xx_ent_wiki_sm": _safe_pkg_version("xx-ent-wiki-sm"),
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "english_model": ENGLISH_MODEL_NAME,
        "hebrew_profile": hebrew_profile,
    }

    _append_nlp_payload(payload, english_analyzer, lang="en", key_prefix="nlp:en")
    _append_nlp_payload(payload, hebrew_analyzer, lang="he", key_prefix="nlp:he")

    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DetectionEngine:
    """Wraps Presidio AnalyzerEngine for PII detection.

    Uses AnalyzerEngine.analyze() only. We do NOT use Presidio's
    AnonymizerEngine -- token replacement is handled by our own
    tokenizer module for deterministic, reversible behavior.
    """

    DEFAULT_SCORE_THRESHOLD = 0.7
    MODEL_LOCK_KEY = "multiengine_en_he_v1"
    LEGACY_MODEL_LOCK_KEYS = ("spacy_multilang_en_he", "en_core_web_lg")

    def __init__(
        self,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        default_language: str = "auto",
        hebrew_backend: str | None = None,
        hebrew_stanza_model: str | None = None,
        hebrew_transformer_model: str | None = None,
    ):
        self._score_threshold = score_threshold
        self._default_language = _normalize_language(default_language)
        self._hebrew_backend = _normalize_hebrew_backend(
            hebrew_backend or os.getenv(HEBREW_BACKEND_ENV, DEFAULT_HEBREW_BACKEND)
        )
        self._hebrew_stanza_model = (
            hebrew_stanza_model
            or os.getenv(HEBREW_STANZA_MODEL_ENV, DEFAULT_HEBREW_STANZA_MODEL)
        ).strip()
        self._hebrew_transformer_model = (
            hebrew_transformer_model
            or os.getenv(HEBREW_TRANSFORMER_MODEL_ENV, DEFAULT_HEBREW_TRANSFORMER_MODEL)
        ).strip()
        self._model_hash: str | None = None
        self._resolved_hebrew_backend: str | None = None
        self._supported_entities_cache: dict[str, list[str]] = {}
        self._cell_detection_cache: dict[tuple[str, str], tuple[DetectedEntity, ...]] = {}
        self._cell_cache_max_entries = 5000
        self._cell_cache_max_text_len = 256

    @property
    def model_lock_key(self) -> str:
        return self.MODEL_LOCK_KEY

    @property
    def legacy_model_lock_keys(self) -> tuple[str, ...]:
        return self.LEGACY_MODEL_LOCK_KEYS

    def resolve_language(self, text: str, language: str | None = None) -> str:
        requested = self._default_language if language is None else _normalize_language(language)
        if requested == "auto":
            return _auto_detect_language(text)
        return requested

    def get_model_hash(self) -> str:
        """Return a deterministic hash of the loaded detection model environment."""
        if self._model_hash is None:
            english_analyzer = _get_english_analyzer()
            hebrew_analyzer, profile = self._get_hebrew_analyzer_and_profile()
            self._model_hash = _compute_model_hash(
                english_analyzer,
                hebrew_analyzer,
                hebrew_profile=profile,
            )
        return self._model_hash

    def detect(self, text: str, language: str | None = None) -> list[DetectedEntity]:
        """Detect PII entities in a text string.

        Returns entities sorted by start position (ascending).
        Filters results below the score threshold.
        Resolves overlapping detections by keeping the higher-scored one.
        """
        if not text or not text.strip():
            return []

        resolved_language = self.resolve_language(text, language)
        analyzer = self._get_analyzer_for_language(resolved_language)
        entities_to_analyze = self._target_entities_for_language(analyzer, resolved_language)

        try:
            results = analyzer.analyze(
                text=text,
                entities=entities_to_analyze or None,
                language=resolved_language,
            )
        except Exception as e:
            raise DetectionError(f"Presidio analysis failed: {e}") from e

        results = [r for r in results if r.score >= self._score_threshold]
        results.sort(key=lambda r: r.start)

        resolved_results = []
        for result in results:
            if resolved_results and result.start < resolved_results[-1].end:
                if result.score > resolved_results[-1].score:
                    resolved_results[-1] = result
            else:
                resolved_results.append(result)

        detected_entities: list[DetectedEntity] = []
        for result in resolved_results:
            entity_type = EntityType.from_presidio(result.entity_type)
            if entity_type is None:
                continue
            detected_entities.append(
                DetectedEntity(
                    entity_type=entity_type,
                    text=text[result.start : result.end],
                    start=result.start,
                    end=result.end,
                    score=result.score,
                )
            )
        return detected_entities

    def detect_in_cell(
        self,
        value: str,
        source_id: str,
        language: str | None = None,
    ) -> list[DetectedEntity]:
        """Detect PII in a single cell value, tagging with source location."""
        resolved_language = self.resolve_language(value, language)
        entities = self._detect_in_cell_cached(value, resolved_language)
        return [
            DetectedEntity(
                entity_type=entity.entity_type,
                text=entity.text,
                start=entity.start,
                end=entity.end,
                score=entity.score,
                source_id=source_id,
            )
            for entity in entities
        ]

    def _target_entities_for_language(
        self,
        analyzer: AnalyzerEngine,
        language: str,
    ) -> list[str]:
        cached = self._supported_entities_cache.get(language)
        if cached is not None:
            return cached

        try:
            supported = set(analyzer.get_supported_entities(language=language))
        except Exception:
            supported = set()

        if not supported:
            entities = list(_TARGET_PRESIDIO_ENTITIES)
        else:
            entities = [entity for entity in _TARGET_PRESIDIO_ENTITIES if entity in supported]
            if not entities:
                entities = list(_TARGET_PRESIDIO_ENTITIES)

        self._supported_entities_cache[language] = entities
        return entities

    def _detect_in_cell_cached(
        self,
        value: str,
        resolved_language: str,
    ) -> tuple[DetectedEntity, ...]:
        if len(value) > self._cell_cache_max_text_len:
            return tuple(self.detect(value, resolved_language))

        key = (resolved_language, value)
        cached = self._cell_detection_cache.get(key)
        if cached is not None:
            return cached

        entities = tuple(self.detect(value, resolved_language))
        self._cell_detection_cache[key] = entities
        if len(self._cell_detection_cache) > self._cell_cache_max_entries:
            self._cell_detection_cache.pop(next(iter(self._cell_detection_cache)))
        return entities

    def _get_hebrew_analyzer_and_profile(self) -> tuple[AnalyzerEngine, dict[str, str]]:
        backend = _resolve_hebrew_backend(self._hebrew_backend)
        self._resolved_hebrew_backend = backend
        return _get_hebrew_analyzer(
            backend,
            stanza_model=self._hebrew_stanza_model,
            transformer_model=self._hebrew_transformer_model,
        )

    def _get_analyzer_for_language(self, language: str) -> AnalyzerEngine:
        if language == "en":
            return _get_english_analyzer()
        if language == "he":
            analyzer, _ = self._get_hebrew_analyzer_and_profile()
            return analyzer
        raise DetectionError(f"Unsupported language '{language}'")
