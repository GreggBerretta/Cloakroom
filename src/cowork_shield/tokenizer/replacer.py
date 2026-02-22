"""Offset-aware text replacement engine."""

from __future__ import annotations

from cowork_shield.models import DetectedEntity, EntityType, ReplacementRecord, Token
from cowork_shield.tokenizer.generator import TokenGenerator


class TextReplacer:
    """Replaces detected entities with tokens in a text string.

    Replacements are applied right-to-left (from the end of the string
    backward) to avoid invalidating earlier offset positions.
    """

    def replace_entities(
        self,
        text: str,
        entities: list[DetectedEntity],
        token_generator: TokenGenerator,
        source_file: str = "",
    ) -> tuple[str, list[ReplacementRecord]]:
        """Replace all detected entities in text with their tokens.

        Returns the modified text and a list of replacement records.
        """
        if not entities:
            return text, []

        records: list[ReplacementRecord] = []
        # Sort entities by start position descending (right-to-left)
        sorted_entities = sorted(entities, key=lambda e: e.start, reverse=True)

        for entity in sorted_entities:
            token = token_generator.get_or_create_token(
                entity.text, entity.entity_type, source_file=source_file
            )
            text = text[: entity.start] + token.token_text + text[entity.end :]
            records.append(
                ReplacementRecord(
                    location=entity.source_id,
                    original_value=entity.text,
                    token_text=token.token_text,
                    entity_type=entity.entity_type,
                )
            )

        return text, records

    def restore_tokens(
        self,
        text: str,
        reverse_lookup: dict[str, str],
    ) -> str:
        """Replace all tokens in text with their original values.

        Uses simple string replacement since token format (e.g., PERSON_001)
        is unambiguous and won't appear in normal text.

        Tokens are replaced longest-first to prevent partial matches
        (e.g., CREDIT_CARD_001 before CREDIT_CARD_01 if both existed).
        """
        # Sort by token length descending to prevent partial matches
        for token_text in sorted(reverse_lookup, key=len, reverse=True):
            original_value = reverse_lookup[token_text]
            text = text.replace(token_text, original_value)
        return text
