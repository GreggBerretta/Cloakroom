"""Token regex patterns shared across tokenizer and verification layers."""

from __future__ import annotations

import re

from cowork_shield.models import EntityType

_PREFIXES = sorted((entity_type.token_prefix for entity_type in EntityType), key=len, reverse=True)
_PREFIX_GROUP = "|".join(re.escape(prefix) for prefix in _PREFIXES)

# New ABI (v2): [PERSON_00001]
BRACKET_TOKEN_PATTERN = re.compile(
    rf"\[(?:{_PREFIX_GROUP})_\d{{5}}\]"
)

# Legacy ABI (v1): PERSON_001 / ORG_00012
LEGACY_TOKEN_PATTERN = re.compile(
    rf"\b(?:{_PREFIX_GROUP})_\d{{3,5}}\b"
)

# Accept both formats during restore/verification for backward compatibility.
ANY_TOKEN_PATTERN = re.compile(
    rf"(?:\[(?:{_PREFIX_GROUP})_\d{{5}}\]|\b(?:{_PREFIX_GROUP})_\d{{3,5}}\b)"
)

