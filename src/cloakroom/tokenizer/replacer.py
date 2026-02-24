"""Offset-aware text replacement engine."""

from __future__ import annotations

from cloakroom.models import DetectedEntity, ReplacementRecord
from cloakroom.tokenizer.patterns import ANY_TOKEN_PATTERN
from cloakroom.tokenizer.generator import TokenGenerator


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

        Supports both v2 bracketed tokens and legacy unbracketed tokens.
        """

        if not reverse_lookup:
            return text

        def _replace(match):
            token_text = match.group(0)
            if token_text in reverse_lookup:
                return reverse_lookup[token_text]

            # Backward compatibility across token ABIs.
            if token_text.startswith("[") and token_text.endswith("]"):
                inner = token_text[1:-1]
                if inner in reverse_lookup:
                    return reverse_lookup[inner]
            else:
                wrapped = f"[{token_text}]"
                if wrapped in reverse_lookup:
                    return reverse_lookup[wrapped]

            return token_text

        return ANY_TOKEN_PATTERN.sub(_replace, text)
