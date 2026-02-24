"""Tests for the text replacement engine."""

import os
import unicodedata

from cloakroom.models import DetectedEntity, EntityType
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.tokenizer.replacer import TextReplacer


class TestReplaceEntities:
    def setup_method(self):
        self.replacer = TextReplacer()
        self.gen = TokenGenerator(os.urandom(32))

    def test_single_entity(self):
        entities = [
            DetectedEntity(
                entity_type=EntityType.PERSON,
                text="John Smith",
                start=11,
                end=21,
                score=0.9,
            )
        ]
        result, records = self.replacer.replace_entities(
            "My name is John Smith today.", entities, self.gen
        )
        assert "[PERSON_00001]" in result
        assert "John Smith" not in result
        assert len(records) == 1

    def test_multiple_entities(self):
        text = "John Smith works at Acme Corp in New York."
        entities = [
            DetectedEntity(EntityType.PERSON, "John Smith", 0, 10, 0.9),
            DetectedEntity(EntityType.ORGANIZATION, "Acme Corp", 20, 29, 0.85),
            DetectedEntity(EntityType.LOCATION, "New York", 33, 41, 0.8),
        ]
        result, records = self.replacer.replace_entities(text, entities, self.gen)
        assert "[PERSON_00001]" in result
        assert "[ORG_00001]" in result
        assert "[LOCATION_00001]" in result
        assert len(records) == 3

    def test_entity_at_start(self):
        entities = [
            DetectedEntity(EntityType.PERSON, "John", 0, 4, 0.9),
        ]
        result, _ = self.replacer.replace_entities("John is here.", entities, self.gen)
        assert result.startswith("[PERSON_00001]")

    def test_entity_at_end(self):
        text = "Call John Smith"
        entities = [
            DetectedEntity(EntityType.PERSON, "John Smith", 5, 15, 0.9),
        ]
        result, _ = self.replacer.replace_entities(text, entities, self.gen)
        assert result.endswith("[PERSON_00001]")

    def test_no_entities(self):
        result, records = self.replacer.replace_entities("Hello world", [], self.gen)
        assert result == "Hello world"
        assert records == []


class TestRestoreTokens:
    def setup_method(self):
        self.replacer = TextReplacer()

    def test_single_restore(self):
        lookup = {"[PERSON_00001]": "John Smith"}
        result = self.replacer.restore_tokens("Call [PERSON_00001] today.", lookup)
        assert result == "Call John Smith today."

    def test_multiple_restores(self):
        lookup = {
            "[PERSON_00001]": "John Smith",
            "[ORG_00001]": "Acme Corp",
        }
        result = self.replacer.restore_tokens(
            "[PERSON_00001] works at [ORG_00001].", lookup
        )
        assert result == "John Smith works at Acme Corp."

    def test_restore_legacy_tokens_with_bracketed_lookup(self):
        lookup = {"[PERSON_00001]": "John Smith"}
        result = self.replacer.restore_tokens("Call PERSON_00001 today.", lookup)
        assert result == "Call John Smith today."

    def test_no_tokens(self):
        result = self.replacer.restore_tokens("No tokens here.", {})
        assert result == "No tokens here."

    def test_round_trip(self):
        gen = TokenGenerator(os.urandom(32))
        text = "John Smith emailed jane@example.com from Acme Corp."
        entities = [
            DetectedEntity(EntityType.PERSON, "John Smith", 0, 10, 0.9),
            DetectedEntity(EntityType.EMAIL, "jane@example.com", 19, 35, 0.95),
            DetectedEntity(EntityType.ORGANIZATION, "Acme Corp", 41, 50, 0.85),
        ]

        anonymized, _ = self.replacer.replace_entities(text, entities, gen)
        lookup = gen.get_reverse_lookup()
        restored = self.replacer.restore_tokens(anonymized, lookup)
        assert restored == text

    def test_hebrew_rtl_token_replacement(self):
        gen = TokenGenerator(os.urandom(32))
        text = "שלום ישראל ישראלי"
        entities = [
            DetectedEntity(
                entity_type=EntityType.LOCATION,
                text="ישראל",
                start=5,
                end=10,
                score=0.99,
            )
        ]

        anonymized, _ = self.replacer.replace_entities(text, entities, gen)
        assert anonymized == "שלום [LOCATION_00001] ישראלי"

        restored = self.replacer.restore_tokens(anonymized, gen.get_reverse_lookup())
        assert unicodedata.normalize("NFC", restored) == unicodedata.normalize("NFC", text)
