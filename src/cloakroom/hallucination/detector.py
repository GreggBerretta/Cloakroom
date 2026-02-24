"""Detect hallucinated, mutated, and dropped tokens."""

from __future__ import annotations

import re
from difflib import get_close_matches

from cloakroom.models import HallucinationFlag

TOKEN_SHAPED_PATTERN = re.compile(
    r"(?:\[[A-Z0-9_]+_\d{5}\]|\b[A-Z0-9_]+_\d{3,5}\b)"
)


def _canonical(token_text: str) -> str:
    if token_text.startswith("[") and token_text.endswith("]"):
        return token_text[1:-1]
    return token_text


def detect_token_anomalies(
    text: str,
    known_tokens: set[str],
    expected_tokens: set[str] | None = None,
) -> list[HallucinationFlag]:
    """Detect suspicious token behavior in text.

    - hallucinated: token-shaped string not found in known mappings.
    - mutated: unknown token that closely resembles a known token.
    - dropped: expected token absent from text.
    """

    known_by_canonical = {_canonical(token): token for token in known_tokens}
    known_canonicals = set(known_by_canonical)

    flags: list[HallucinationFlag] = []
    observed_canonicals: set[str] = set()

    for match in TOKEN_SHAPED_PATTERN.finditer(text):
        token_text = match.group(0)
        canonical = _canonical(token_text)
        observed_canonicals.add(canonical)

        if token_text in known_tokens or canonical in known_canonicals:
            continue

        nearest = get_close_matches(canonical, sorted(known_canonicals), n=1, cutoff=0.85)
        if nearest:
            nearest_token = known_by_canonical[nearest[0]]
            flags.append(
                HallucinationFlag(
                    token_text=token_text,
                    flag_type="mutated",
                    nearest_match=nearest_token,
                    position=match.start(),
                )
            )
            continue

        flags.append(
            HallucinationFlag(
                token_text=token_text,
                flag_type="hallucinated",
                nearest_match=None,
                position=match.start(),
            )
        )

    if expected_tokens:
        expected_canonicals = {_canonical(token) for token in expected_tokens}
        dropped_canonicals = sorted(expected_canonicals - observed_canonicals)
        for dropped in dropped_canonicals:
            nearest_token = known_by_canonical.get(dropped, dropped)
            flags.append(
                HallucinationFlag(
                    token_text=nearest_token,
                    flag_type="dropped",
                    nearest_match=None,
                    position=-1,
                )
            )

    return flags
