"""Entity type registry and value normalization."""

from __future__ import annotations

import re

from cloakroom.models import EntityType

# Cloakroom-specific types that are never requested from Presidio. They are
# produced by the regex prefilter, the demo-rule pre-pass, or post-detection
# promotion (e.g. HE_PERSON for Hebrew-script PERSON results).
_CLOAKROOM_ONLY_TYPES = {
    EntityType.COLUMN,
    EntityType.HE_PERSON,
    EntityType.TEUDAT_ZEHUT,
    EntityType.IL_PHONE,
    EntityType.IL_ADDRESS,
    EntityType.IL_BANK_ACCOUNT,
    EntityType.PROJECT,
    EntityType.CONTRACT_VALUE,
    EntityType.PRICING_TERM,
    EntityType.STRATEGY,
    EntityType.ADDRESS_LINE,
    EntityType.CUSTOMER_ID,
}

# Presidio entity type strings we actively detect via NER.
SUPPORTED_PRESIDIO_ENTITIES: list[str] = [
    member.value for member in EntityType if member not in _CLOAKROOM_ONLY_TYPES
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
