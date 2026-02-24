"""Entity type registry and value normalization."""

from __future__ import annotations

import re

from cloakroom.models import EntityType

# Presidio entity type strings we actively detect.
# COLUMN is internal-only and must never be requested from Presidio.
SUPPORTED_PRESIDIO_ENTITIES: list[str] = [
    member.value for member in EntityType if member != EntityType.COLUMN
]


def normalize_entity_value(value: str, entity_type: EntityType) -> str:
    """Normalize an entity value for consistent deduplication.

    Same original value (after normalization) always maps to the same token
    within a workspace.
    """
    value = value.strip()
    if entity_type == EntityType.EMAIL:
        return value.lower()
    if entity_type == EntityType.PHONE:
        return re.sub(r"[^\d]", "", value)
    # Default: lowercase, collapse internal whitespace
    return re.sub(r"\s+", " ", value.lower())


def make_mapping_key(entity_type: EntityType, normalized_value: str) -> str:
    """Create the vault mapping key for a (type, value) pair.

    Format: {entity_type_value}::{normalized_value}
    This ensures uniqueness across types (e.g., a person named "Amazon"
    and the org "Amazon" get separate tokens).
    """
    return f"{entity_type.value}::{normalized_value}"
