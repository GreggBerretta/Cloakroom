"""Tests for deterministic token generation."""

import os

from cowork_shield.models import EntityType
from cowork_shield.tokenizer.generator import TokenGenerator, compute_hmac


class TestComputeHmac:
    def test_deterministic(self):
        key = os.urandom(32)
        h1 = compute_hmac("PERSON_00001", "John Smith", key)
        h2 = compute_hmac("PERSON_00001", "John Smith", key)
        assert h1 == h2

    def test_different_inputs(self):
        key = os.urandom(32)
        h1 = compute_hmac("PERSON_00001", "John Smith", key)
        h2 = compute_hmac("PERSON_00001", "Jane Doe", key)
        assert h1 != h2

    def test_different_keys(self):
        k1 = os.urandom(32)
        k2 = os.urandom(32)
        h1 = compute_hmac("PERSON_00001", "John Smith", k1)
        h2 = compute_hmac("PERSON_00001", "John Smith", k2)
        assert h1 != h2


class TestTokenGenerator:
    def setup_method(self):
        self.hmac_key = os.urandom(32)
        self.gen = TokenGenerator(self.hmac_key)

    def test_creates_token(self):
        token = self.gen.get_or_create_token("John Smith", EntityType.PERSON)
        assert token.token_text == "[PERSON_00001]"
        assert token.entity_type == EntityType.PERSON
        assert token.hmac_tag  # non-empty

    def test_deterministic_same_value(self):
        t1 = self.gen.get_or_create_token("John Smith", EntityType.PERSON)
        t2 = self.gen.get_or_create_token("John Smith", EntityType.PERSON)
        assert t1.token_text == t2.token_text
        assert t1.hmac_tag == t2.hmac_tag

    def test_case_insensitive_normalization(self):
        t1 = self.gen.get_or_create_token("John Smith", EntityType.PERSON)
        t2 = self.gen.get_or_create_token("john smith", EntityType.PERSON)
        assert t1.token_text == t2.token_text

    def test_different_values_different_tokens(self):
        t1 = self.gen.get_or_create_token("John Smith", EntityType.PERSON)
        t2 = self.gen.get_or_create_token("Jane Doe", EntityType.PERSON)
        assert t1.token_text != t2.token_text
        assert t1.token_text == "[PERSON_00001]"
        assert t2.token_text == "[PERSON_00002]"

    def test_cross_type_separation(self):
        t1 = self.gen.get_or_create_token("Amazon", EntityType.PERSON)
        t2 = self.gen.get_or_create_token("Amazon", EntityType.ORGANIZATION)
        assert t1.token_text != t2.token_text
        assert t1.token_text == "[PERSON_00001]"
        assert t2.token_text == "[ORG_00001]"

    def test_counter_incrementing(self):
        self.gen.get_or_create_token("Alice", EntityType.PERSON)
        self.gen.get_or_create_token("Bob", EntityType.PERSON)
        t3 = self.gen.get_or_create_token("Charlie", EntityType.PERSON)
        assert t3.token_text == "[PERSON_00003]"

    def test_verify_token_success(self):
        token = self.gen.get_or_create_token("John Smith", EntityType.PERSON)
        assert self.gen.verify_token(token, "John Smith")

    def test_verify_token_wrong_original(self):
        token = self.gen.get_or_create_token("John Smith", EntityType.PERSON)
        assert not self.gen.verify_token(token, "Jane Doe")

    def test_get_mapping(self):
        self.gen.get_or_create_token("John Smith", EntityType.PERSON)
        mapping = self.gen.get_mapping("[PERSON_00001]")
        assert mapping is not None
        assert mapping.original_value == "John Smith"

    def test_get_reverse_lookup(self):
        self.gen.get_or_create_token("John Smith", EntityType.PERSON)
        self.gen.get_or_create_token("Acme Corp", EntityType.ORGANIZATION)
        lookup = self.gen.get_reverse_lookup()
        assert lookup["[PERSON_00001]"] == "John Smith"
        assert lookup["[ORG_00001]"] == "Acme Corp"

    def test_state_export_import(self):
        self.gen.get_or_create_token("John Smith", EntityType.PERSON)
        self.gen.get_or_create_token("Acme Corp", EntityType.ORGANIZATION)

        counters, mappings = self.gen.export_state()

        # Create new generator and restore state
        gen2 = TokenGenerator(self.hmac_key)
        gen2.load_state(counters, mappings)

        # Same value should return same token (not create new)
        token = gen2.get_or_create_token("John Smith", EntityType.PERSON)
        assert token.token_text == "[PERSON_00001]"

        # New value should continue from counter
        token2 = gen2.get_or_create_token("Jane Doe", EntityType.PERSON)
        assert token2.token_text == "[PERSON_00002]"

    def test_source_file_tracking(self):
        self.gen.get_or_create_token("John Smith", EntityType.PERSON, source_file="a.xlsx")
        self.gen.get_or_create_token("John Smith", EntityType.PERSON, source_file="b.docx")

        mapping = self.gen.get_mapping("[PERSON_00001]")
        assert "a.xlsx" in mapping.source_files
        assert "b.docx" in mapping.source_files
