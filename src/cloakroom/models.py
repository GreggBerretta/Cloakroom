"""Core data models for Cloakroom."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol


class EntityType(str, Enum):
    """Supported PII and confidential-data entity types.

    Members whose .value matches a Presidio entity string are produced by
    Presidio NER. Members whose .value is Cloakroom-specific (e.g. PROJECT,
    TEUDAT_ZEHUT) are produced only by the regex prefilter, the demo-rule
    pre-pass, or post-detection promotion (e.g. HE_PERSON).
    """

    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    EMAIL = "EMAIL_ADDRESS"
    PHONE = "PHONE_NUMBER"
    SSN = "US_SSN"
    CREDIT_CARD = "CREDIT_CARD"
    DATE = "DATE_TIME"
    IP_ADDRESS = "IP_ADDRESS"
    URL = "URL"
    COLUMN = "COLUMN"

    # Israeli/Hebrew first-class types
    HE_PERSON = "HE_PERSON"
    TEUDAT_ZEHUT = "TEUDAT_ZEHUT"
    IL_PHONE = "IL_PHONE"
    IL_ADDRESS = "IL_ADDRESS"
    IL_BANK_ACCOUNT = "IL_BANK_ACCOUNT"

    # Confidential business data types (driven by demo rules)
    PROJECT = "PROJECT"
    CONTRACT_VALUE = "CONTRACT_VALUE"
    PRICING_TERM = "PRICING_TERM"
    STRATEGY = "STRATEGY"
    ADDRESS_LINE = "ADDRESS_LINE"
    CUSTOMER_ID = "CUSTOMER_ID"

    @property
    def token_prefix(self) -> str:
        """Short prefix used in token format (e.g., PERSON, ORG)."""
        _prefixes = {
            EntityType.PERSON: "PERSON",
            EntityType.ORGANIZATION: "ORG",
            EntityType.LOCATION: "LOCATION",
            EntityType.EMAIL: "EMAIL",
            EntityType.PHONE: "PHONE",
            EntityType.SSN: "SSN",
            EntityType.CREDIT_CARD: "CREDIT_CARD",
            EntityType.DATE: "DATE",
            EntityType.IP_ADDRESS: "IP",
            EntityType.URL: "URL",
            EntityType.COLUMN: "COL",
            EntityType.HE_PERSON: "HE_PERSON",
            EntityType.TEUDAT_ZEHUT: "TEUDAT_ZEHUT",
            EntityType.IL_PHONE: "IL_PHONE",
            EntityType.IL_ADDRESS: "IL_ADDRESS",
            EntityType.IL_BANK_ACCOUNT: "IL_BANK_ACCOUNT",
            EntityType.PROJECT: "PROJECT",
            EntityType.CONTRACT_VALUE: "CONTRACT_VALUE",
            EntityType.PRICING_TERM: "PRICING_TERM",
            EntityType.STRATEGY: "STRATEGY",
            EntityType.ADDRESS_LINE: "ADDRESS",
            EntityType.CUSTOMER_ID: "CUSTOMER_ID",
        }
        return _prefixes[self]

    @classmethod
    def from_presidio(cls, presidio_type: str) -> EntityType | None:
        """Convert a Presidio entity type string to our EntityType enum.

        Returns None if the type is not supported.
        """
        for member in cls:
            if member.value == presidio_type:
                return member
        return None


@dataclass(frozen=True)
class DetectedEntity:
    """A single PII entity detected in a document."""

    entity_type: EntityType
    text: str
    start: int
    end: int
    score: float
    source_id: str = ""


@dataclass(frozen=True)
class Token:
    """A deterministic replacement token with HMAC integrity tag.

    Format: [{PREFIX}_{NNNNN}] (e.g., [PERSON_00001], [ORG_00002])
    """

    token_text: str
    entity_type: EntityType
    hmac_tag: str


@dataclass
class EntityMapping:
    """Bidirectional mapping between an original value and its token.

    One EntityMapping exists per unique (entity_type, normalized_original)
    pair in the workspace.
    """

    token: Token
    original_value: str
    normalized_key: str
    entity_type: EntityType
    first_seen: str
    source_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "token_text": self.token.token_text,
            "entity_type": self.entity_type.value,
            "hmac_tag": self.token.hmac_tag,
            "original_value": self.original_value,
            "normalized_key": self.normalized_key,
            "first_seen": self.first_seen,
            "source_files": self.source_files,
        }

    @classmethod
    def from_dict(cls, data: dict) -> EntityMapping:
        entity_type = EntityType(data["entity_type"])
        token = Token(
            token_text=data["token_text"],
            entity_type=entity_type,
            hmac_tag=data["hmac_tag"],
        )
        return cls(
            token=token,
            original_value=data["original_value"],
            normalized_key=data["normalized_key"],
            entity_type=entity_type,
            first_seen=data["first_seen"],
            source_files=data.get("source_files", []),
        )


@dataclass
class FileRecord:
    """Metadata about a single file processed in the workspace."""

    file_path: str
    file_hash_before: str
    file_hash_after: str
    anonymized_path: str
    entities_found: int
    tokens_applied: int
    timestamp: str
    format: str
    model_hash: str = ""
    applied_tokens: list[str] = field(default_factory=list)
    reanonymize_override: bool = False
    override_reason: str = ""
    override_user: str = ""
    override_timestamp: str = ""
    previous_output_hash: str = ""
    override_events: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "file_hash_before": self.file_hash_before,
            "file_hash_after": self.file_hash_after,
            "anonymized_path": self.anonymized_path,
            "entities_found": self.entities_found,
            "tokens_applied": self.tokens_applied,
            "timestamp": self.timestamp,
            "format": self.format,
            "model_hash": self.model_hash,
            "applied_tokens": self.applied_tokens,
            "reanonymize_override": self.reanonymize_override,
            "override_reason": self.override_reason,
            "override_user": self.override_user,
            "override_timestamp": self.override_timestamp,
            "previous_output_hash": self.previous_output_hash,
            "override_events": self.override_events,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FileRecord:
        return cls(
            file_path=data["file_path"],
            file_hash_before=data["file_hash_before"],
            file_hash_after=data["file_hash_after"],
            anonymized_path=data["anonymized_path"],
            entities_found=data["entities_found"],
            tokens_applied=data["tokens_applied"],
            timestamp=data["timestamp"],
            format=data["format"],
            model_hash=data.get("model_hash", ""),
            applied_tokens=data.get("applied_tokens", []),
            reanonymize_override=data.get("reanonymize_override", False),
            override_reason=data.get("override_reason", ""),
            override_user=data.get("override_user", ""),
            override_timestamp=data.get("override_timestamp", ""),
            previous_output_hash=data.get("previous_output_hash", ""),
            override_events=data.get("override_events", []),
        )


@dataclass
class VaultData:
    """The complete vault contents, serialized to encrypted JSON.

    Version 2.0 includes governance controls (self-destruct on restore) on top of
    observability metadata, behavioral prompt tracking, detection model hashes,
    and token ABI versioning.
    """

    workspace_id: str
    workspace_name: str
    created_at: str
    updated_at: str
    ttl_hours: int
    mappings: dict[str, EntityMapping] = field(default_factory=dict)
    token_counter: dict[str, int] = field(default_factory=dict)
    file_records: list[FileRecord] = field(default_factory=list)
    vault_version: str = "2.0"

    # --- Phase 2 v2.0 fields ---

    # Observability counters
    anonymize_count: int = 0
    restore_count: int = 0
    abort_count: int = 0
    last_used: str = ""
    shipped_client_work: bool = False
    workspace_recall_type: str = ""  # "manual" | "command" | "menu_bar"

    # Behavioral prompt responses
    trust_flip_responses: list[dict] = field(default_factory=list)
    rewrite_avoidance_responses: list[dict] = field(default_factory=list)
    pre_llm_capture_responses: list[dict] = field(default_factory=list)

    # Attestation tracking
    attestation_records: list[dict] = field(default_factory=list)
    attestation_completion_time: list[float] = field(default_factory=list)
    attestation_abort_count: int = 0

    # Timing data
    time_to_close_after_restore: list[float] = field(default_factory=list)

    # Detection version lock
    model_hashes: dict[str, str] = field(default_factory=dict)

    # Token format version
    token_abi_version: str = "v2"

    # Vault governance v1
    self_destruct_on_restore: bool = False

    def to_dict(self) -> dict:
        return {
            "vault_version": self.vault_version,
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ttl_hours": self.ttl_hours,
            "token_counter": self.token_counter,
            "mappings": {k: v.to_dict() for k, v in self.mappings.items()},
            "file_records": [r.to_dict() for r in self.file_records],
            # v2.0 fields
            "anonymize_count": self.anonymize_count,
            "restore_count": self.restore_count,
            "abort_count": self.abort_count,
            "last_used": self.last_used,
            "shipped_client_work": self.shipped_client_work,
            "workspace_recall_type": self.workspace_recall_type,
            "trust_flip_responses": self.trust_flip_responses,
            "rewrite_avoidance_responses": self.rewrite_avoidance_responses,
            "pre_llm_capture_responses": self.pre_llm_capture_responses,
            "attestation_records": self.attestation_records,
            "attestation_completion_time": self.attestation_completion_time,
            "attestation_abort_count": self.attestation_abort_count,
            "time_to_close_after_restore": self.time_to_close_after_restore,
            "model_hashes": self.model_hashes,
            "token_abi_version": self.token_abi_version,
            "self_destruct_on_restore": self.self_destruct_on_restore,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VaultData:
        mappings = {
            k: EntityMapping.from_dict(v) for k, v in data.get("mappings", {}).items()
        }
        file_records = [FileRecord.from_dict(r) for r in data.get("file_records", [])]
        return cls(
            vault_version=data.get("vault_version", "1.0"),
            workspace_id=data["workspace_id"],
            workspace_name=data["workspace_name"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            ttl_hours=data["ttl_hours"],
            token_counter=data.get("token_counter", {}),
            mappings=mappings,
            file_records=file_records,
            # v2.0 fields with safe defaults
            anonymize_count=data.get("anonymize_count", 0),
            restore_count=data.get("restore_count", 0),
            abort_count=data.get("abort_count", 0),
            last_used=data.get("last_used", ""),
            shipped_client_work=data.get("shipped_client_work", False),
            workspace_recall_type=data.get("workspace_recall_type", ""),
            trust_flip_responses=data.get("trust_flip_responses", []),
            rewrite_avoidance_responses=data.get("rewrite_avoidance_responses", []),
            pre_llm_capture_responses=data.get("pre_llm_capture_responses", []),
            attestation_records=data.get("attestation_records", []),
            attestation_completion_time=data.get("attestation_completion_time", []),
            attestation_abort_count=data.get("attestation_abort_count", 0),
            time_to_close_after_restore=data.get("time_to_close_after_restore", []),
            model_hashes=data.get("model_hashes", {}),
            token_abi_version=data.get("token_abi_version", "v1"),
            self_destruct_on_restore=data.get("self_destruct_on_restore", False),
        )


@dataclass
class AttestationRecord:
    """Record of a user attestation review before anonymization."""

    timestamp: str
    user: str  # from os.getlogin() or "cli"
    entity_count: int
    entity_types: dict[str, int]  # type -> count
    completion_time_seconds: float
    confirmed: bool
    file_path: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "user": self.user,
            "entity_count": self.entity_count,
            "entity_types": self.entity_types,
            "completion_time_seconds": self.completion_time_seconds,
            "confirmed": self.confirmed,
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AttestationRecord:
        return cls(
            timestamp=data["timestamp"],
            user=data["user"],
            entity_count=data["entity_count"],
            entity_types=data["entity_types"],
            completion_time_seconds=data["completion_time_seconds"],
            confirmed=data["confirmed"],
            file_path=data["file_path"],
        )


@dataclass(frozen=True)
class HallucinationFlag:
    """A flagged token in restored text that was not in the original vault."""

    token_text: str
    flag_type: str  # "hallucinated" | "mutated" | "dropped"
    nearest_match: str | None  # for mutated tokens
    position: int  # character offset in restored text

    def to_dict(self) -> dict:
        return {
            "token_text": self.token_text,
            "flag_type": self.flag_type,
            "nearest_match": self.nearest_match,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: dict) -> HallucinationFlag:
        return cls(
            token_text=data["token_text"],
            flag_type=data["flag_type"],
            nearest_match=data.get("nearest_match"),
            position=data["position"],
        )


@dataclass(frozen=True)
class ReplacementRecord:
    """Tracks a specific replacement in a specific file location."""

    location: str
    original_value: str
    token_text: str
    entity_type: EntityType


class Clock(Protocol):
    """Clock abstraction to support deterministic replay tests."""

    def now_iso(self) -> str:
        """Return current UTC time as ISO 8601 string."""


class SystemClock:
    """Production clock implementation."""

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class FrozenClock:
    """Deterministic clock for replay and tests."""

    def __init__(self, fixed_time: str):
        self._fixed_time = fixed_time

    def now_iso(self) -> str:
        return self._fixed_time


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return SystemClock().now_iso()
