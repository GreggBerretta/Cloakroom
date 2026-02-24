"""Presidio AnalyzerEngine wrapper for PII detection."""

from __future__ import annotations

from dataclasses import dataclass
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

from cowork_shield.detection.regex_prefilter import RegexPreFilter
from cowork_shield.exceptions import DetectionError
from cowork_shield.models import DetectedEntity, EntityType

SUPPORTED_LANGUAGES = ("en", "he")
LANGUAGE_CHOICES = ("auto", "en", "he")
HEBREW_BACKEND_CHOICES = ("auto", "spacy", "stanza", "transformers")
DETECTION_MODE_CHOICES = ("speed", "balanced", "accurate")

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


@dataclass(frozen=True)
class DetectionProfile:
    mode: str
    regex_enabled: bool
    regex_only: bool
    ner_batch_size: int


@dataclass(frozen=True)
class _NerTemplate:
    entity_type: EntityType
    start: int
    end: int
    score: float


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


def _normalize_detection_mode(mode: str) -> str:
    value = (mode or "balanced").strip().lower()
    if value not in DETECTION_MODE_CHOICES:
        raise DetectionError(
            "Unsupported detection mode "
            f"'{mode}'. Expected one of: {', '.join(DETECTION_MODE_CHOICES)}"
        )
    return value


def _resolve_detection_profile(mode: str) -> DetectionProfile:
    normalized = _normalize_detection_mode(mode)
    if normalized == "speed":
        return DetectionProfile(
            mode=normalized,
            regex_enabled=True,
            regex_only=False,
            ner_batch_size=250,
        )
    if normalized == "accurate":
        return DetectionProfile(
            mode=normalized,
            regex_enabled=True,
            regex_only=False,
            ner_batch_size=80,
        )
    return DetectionProfile(
        mode=normalized,
        regex_enabled=True,
        regex_only=False,
        ner_batch_size=150,
    )


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
        detection_mode: str = "balanced",
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
        self._profile = _resolve_detection_profile(detection_mode)
        self._regex_prefilter = RegexPreFilter()
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

    @property
    def detection_mode(self) -> str:
        return self._profile.mode

    @property
    def ner_batch_size(self) -> int:
        return self._profile.ner_batch_size

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
        regex_entities = self._detect_regex_entities(text, resolved_language)
        if self._profile.regex_only:
            return regex_entities

        masked_text = self._mask_spans(text, regex_entities)
        if not self._should_run_ner(masked_text):
            return regex_entities

        ner_entities = self._detect_ner_entities(masked_text, text, resolved_language)
        merged = self._merge_entities(regex_entities, ner_entities)
        return merged

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

    def detect_many(
        self,
        texts: list[str],
        *,
        source_ids: list[str] | None = None,
        language: str | None = None,
    ) -> list[list[DetectedEntity]]:
        """Detect entities across many text inputs using chunked NER calls."""
        if not texts:
            return []

        ids = source_ids or ["" for _ in texts]
        if len(ids) != len(texts):
            raise DetectionError("source_ids length must match texts length")

        grouped: dict[str, list[int]] = {}
        for idx, text in enumerate(texts):
            resolved = self.resolve_language(text, language)
            grouped.setdefault(resolved, []).append(idx)

        results: list[list[DetectedEntity]] = [[] for _ in texts]
        for resolved_language, indices in grouped.items():
            batch_size = max(1, self._profile.ner_batch_size)
            for offset in range(0, len(indices), batch_size):
                chunk_indices = indices[offset : offset + batch_size]
                chunk_texts = [texts[i] for i in chunk_indices]
                chunk_ids = [ids[i] for i in chunk_indices]
                chunk_results = self._detect_many_same_language(
                    chunk_texts,
                    source_ids=chunk_ids,
                    language=resolved_language,
                )
                for local_idx, global_idx in enumerate(chunk_indices):
                    results[global_idx] = chunk_results[local_idx]
        return results

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

    def _detect_regex_entities(self, text: str, language: str) -> list[DetectedEntity]:
        if not self._profile.regex_enabled:
            return []
        entities = self._regex_prefilter.extract_entities(text, language=language)
        return [entity for entity in entities if entity.score >= self._score_threshold]

    def _detect_ner_entities(
        self,
        masked_text: str,
        original_text: str,
        language: str,
    ) -> list[DetectedEntity]:
        analyzer = self._get_analyzer_for_language(language)
        entities_to_analyze = self._target_entities_for_language(analyzer, language)

        try:
            results = analyzer.analyze(
                text=masked_text,
                entities=entities_to_analyze or None,
                language=language,
            )
        except Exception as e:
            raise DetectionError(f"Presidio analysis failed: {e}") from e

        detected: list[DetectedEntity] = []
        for result in results:
            if result.score < self._score_threshold:
                continue
            entity_type = EntityType.from_presidio(result.entity_type)
            if entity_type is None:
                continue
            detected.append(
                DetectedEntity(
                    entity_type=entity_type,
                    text=original_text[result.start : result.end],
                    start=result.start,
                    end=result.end,
                    score=result.score,
                )
            )
        return detected

    def _merge_entities(
        self,
        regex_entities: list[DetectedEntity],
        ner_entities: list[DetectedEntity],
    ) -> list[DetectedEntity]:
        merged = sorted(regex_entities + ner_entities, key=lambda item: (item.start, -item.score))
        resolved: list[DetectedEntity] = []
        for entity in merged:
            if entity.start >= entity.end:
                continue
            if resolved and entity.start < resolved[-1].end:
                if entity.score > resolved[-1].score:
                    resolved[-1] = entity
                continue
            resolved.append(entity)
        return resolved

    @staticmethod
    def _mask_spans(text: str, entities: list[DetectedEntity]) -> str:
        if not entities:
            return text
        chars = list(text)
        for entity in entities:
            for idx in range(entity.start, min(entity.end, len(chars))):
                chars[idx] = " "
        return "".join(chars)

    def _should_run_ner(self, masked_text: str) -> bool:
        stripped = masked_text.strip()
        if not stripped:
            return False
        if self._profile.mode != "speed":
            return True
        # In speed mode skip expensive NER on tiny residual fragments.
        return sum(1 for char in stripped if char.isalnum()) >= 12

    def _detect_many_same_language(
        self,
        texts: list[str],
        *,
        source_ids: list[str],
        language: str,
    ) -> list[list[DetectedEntity]]:
        if not texts:
            return []

        analyzer = self._get_analyzer_for_language(language)
        entities_to_analyze = self._target_entities_for_language(analyzer, language)

        regex_entities_by_idx: list[list[DetectedEntity]] = []
        masked_text_by_idx: list[str] = []
        run_ner_by_idx: list[bool] = []

        for text in texts:
            regex_entities = self._detect_regex_entities(text, language)
            regex_entities_by_idx.append(regex_entities)

            if self._profile.regex_only:
                masked_text_by_idx.append("")
                run_ner_by_idx.append(False)
                continue

            masked_text = self._mask_spans(text, regex_entities)
            masked_text_by_idx.append(masked_text)
            run_ner_by_idx.append(self._should_run_ner(masked_text))

        ner_templates_cache: dict[str, list[_NerTemplate]] = {}
        ner_entities_by_idx: list[list[DetectedEntity]] = [[] for _ in texts]
        for idx, text in enumerate(texts):
            if not run_ner_by_idx[idx]:
                continue

            masked_text = masked_text_by_idx[idx]
            cache_key = self._canonicalize_ner_text(masked_text)
            templates = ner_templates_cache.get(cache_key)
            if templates is None:
                templates = self._analyze_ner_templates(
                    analyzer=analyzer,
                    text=cache_key,
                    language=language,
                    entities_to_analyze=entities_to_analyze,
                )
                ner_templates_cache[cache_key] = templates

            ner_entities_by_idx[idx] = self._materialize_ner_entities(
                templates,
                original_text=text,
            )

        results: list[list[DetectedEntity]] = []
        for idx in range(len(texts)):
            merged = self._merge_entities(regex_entities_by_idx[idx], ner_entities_by_idx[idx])
            results.append(
                [
                    DetectedEntity(
                        entity_type=entity.entity_type,
                        text=entity.text,
                        start=entity.start,
                        end=entity.end,
                        score=entity.score,
                        source_id=source_ids[idx],
                    )
                    for entity in merged
                ]
            )
        return results

    def _analyze_ner_templates(
        self,
        *,
        analyzer: AnalyzerEngine,
        text: str,
        language: str,
        entities_to_analyze: list[str],
    ) -> list[_NerTemplate]:
        try:
            results = analyzer.analyze(
                text=text,
                entities=entities_to_analyze or None,
                language=language,
            )
        except Exception as e:
            raise DetectionError(f"Presidio analysis failed: {e}") from e

        templates: list[_NerTemplate] = []
        for result in results:
            if result.score < self._score_threshold:
                continue
            entity_type = EntityType.from_presidio(result.entity_type)
            if entity_type is None:
                continue
            if result.start >= result.end:
                continue
            templates.append(
                _NerTemplate(
                    entity_type=entity_type,
                    start=result.start,
                    end=result.end,
                    score=result.score,
                )
            )
        templates.sort(key=lambda item: item.start)
        return templates

    @staticmethod
    def _canonicalize_ner_text(text: str) -> str:
        if not text:
            return text
        return "".join("0" if char.isdigit() else char for char in text)

    def _materialize_ner_entities(
        self,
        templates: list[_NerTemplate],
        *,
        original_text: str,
    ) -> list[DetectedEntity]:
        text_len = len(original_text)
        entities: list[DetectedEntity] = []
        for template in templates:
            if template.start < 0 or template.end > text_len:
                continue
            if template.start >= template.end:
                continue
            entities.append(
                DetectedEntity(
                    entity_type=template.entity_type,
                    text=original_text[template.start : template.end],
                    start=template.start,
                    end=template.end,
                    score=template.score,
                )
            )
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
