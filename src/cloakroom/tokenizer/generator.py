"""Deterministic token generation with HMAC integrity."""

from __future__ import annotations

import hashlib
import hmac as hmac_module
import re

from cloakroom.detection.entity_types import make_mapping_key, normalize_entity_value
from cloakroom.models import Clock, EntityMapping, EntityType, SystemClock, Token


def compute_hmac(token_text: str, original_value: str, hmac_key: bytes) -> str:
    """Compute HMAC-SHA256 over token+original to detect tampering."""
    message = f"{token_text}:{original_value}".encode("utf-8")
    return hmac_module.new(hmac_key, message, hashlib.sha256).hexdigest()


class TokenGenerator:
    """Generates deterministic, HMAC-tagged tokens for detected entities.

    Workspace-scoped: the same generator instance is used across all files
    in a workspace to ensure cross-file consistency (same person = same token).
    """

    def __init__(self, hmac_key: bytes, clock: Clock | None = None):
        self._hmac_key = hmac_key
        self._counters: dict[str, int] = {}  # token_prefix -> next counter
        self._registry: dict[str, EntityMapping] = {}  # mapping_key -> EntityMapping
        self._clock = clock or SystemClock()

    def get_or_create_token(
        self,
        original_value: str,
        entity_type: EntityType,
        source_file: str = "",
    ) -> Token:
        """Return existing token for this value, or create a new one.

        Guarantees: same (normalized_value, entity_type) -> same Token.
        """
        normalized = normalize_entity_value(original_value, entity_type)
        mapping_key = make_mapping_key(entity_type, normalized)

        if mapping_key in self._registry:
            mapping = self._registry[mapping_key]
            if source_file and source_file not in mapping.source_files:
                mapping.source_files.append(source_file)
            return mapping.token

        # Create new token
        prefix = entity_type.token_prefix
        counter = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = counter

        token_text = f"[{prefix}_{counter:05d}]"
        tag = compute_hmac(token_text, original_value, self._hmac_key)

        token = Token(token_text=token_text, entity_type=entity_type, hmac_tag=tag)

        mapping = EntityMapping(
            token=token,
            original_value=original_value,
            normalized_key=mapping_key,
            entity_type=entity_type,
            first_seen=self._clock.now_iso(),
            source_files=[source_file] if source_file else [],
        )
        self._registry[mapping_key] = mapping

        return token

    def get_or_create_column_token(
        self,
        original_value: str,
        column_prefix: str,
        source_file: str = "",
    ) -> Token:
        """Return existing token for a user-selected column value, or create one."""
        normalized = normalize_entity_value(original_value, EntityType.COLUMN)
        prefix = _normalize_column_prefix(column_prefix)
        mapping_key = f"{EntityType.COLUMN.value}:{prefix}::{normalized}"

        if mapping_key in self._registry:
            mapping = self._registry[mapping_key]
            if source_file and source_file not in mapping.source_files:
                mapping.source_files.append(source_file)
            return mapping.token

        counter_key = f"{EntityType.COLUMN.token_prefix}:{prefix}"
        counter = self._counters.get(counter_key, 0) + 1
        self._counters[counter_key] = counter

        token_text = f"[{prefix}_{counter:05d}]"
        tag = compute_hmac(token_text, original_value, self._hmac_key)

        token = Token(
            token_text=token_text,
            entity_type=EntityType.COLUMN,
            hmac_tag=tag,
        )

        mapping = EntityMapping(
            token=token,
            original_value=original_value,
            normalized_key=mapping_key,
            entity_type=EntityType.COLUMN,
            first_seen=self._clock.now_iso(),
            source_files=[source_file] if source_file else [],
        )
        self._registry[mapping_key] = mapping
        return token

    def get_mapping(self, token_text: str) -> EntityMapping | None:
        """Look up an entity mapping by its token text."""
        for mapping in self._registry.values():
            if mapping.token.token_text == token_text:
                return mapping
        return None

    def verify_token(self, token: Token, original_value: str) -> bool:
        """Verify HMAC integrity of a token-to-original mapping."""
        expected = compute_hmac(token.token_text, original_value, self._hmac_key)
        return hmac_module.compare_digest(token.hmac_tag, expected)

    def get_all_mappings(self) -> dict[str, EntityMapping]:
        """Return all registered mappings."""
        return dict(self._registry)

    def get_reverse_lookup(self) -> dict[str, str]:
        """Build token_text -> original_value lookup for restoration."""
        return {
            m.token.token_text: m.original_value for m in self._registry.values()
        }

    def load_state(
        self,
        counters: dict[str, int],
        mappings: dict[str, EntityMapping],
    ) -> None:
        """Restore generator state from vault (for resuming a workspace)."""
        self._counters = dict(counters)
        self._registry = dict(mappings)

    def export_state(self) -> tuple[dict[str, int], dict[str, EntityMapping]]:
        """Export current state for vault persistence."""
        return dict(self._counters), dict(self._registry)


def _normalize_column_prefix(column_prefix: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", (column_prefix or "").strip().upper())
    cleaned = cleaned.strip("_")
    if not cleaned:
        return "COL"
    if cleaned[0].isdigit():
        cleaned = f"C{cleaned}"
    return cleaned[:64]
