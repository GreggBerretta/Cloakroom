"""Tests for the integrity verifier."""

import os

import pytest

from cowork_shield.models import EntityMapping, EntityType, Token
from cowork_shield.tokenizer.generator import TokenGenerator
from cowork_shield.verification.verifier import IntegrityVerifier, compute_sha256


@pytest.fixture
def hmac_key():
    return os.urandom(32)


@pytest.fixture
def generator(hmac_key):
    return TokenGenerator(hmac_key)


@pytest.fixture
def verifier(generator):
    return IntegrityVerifier(generator)


class TestComputeSha256:
    def test_deterministic(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello")
        h1 = compute_sha256(f)
        h2 = compute_sha256(f)
        assert h1 == h2

    def test_different_content(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("Hello")
        f2.write_text("World")
        assert compute_sha256(f1) != compute_sha256(f2)


class TestVerifyAllHmacs:
    def test_all_valid(self, generator, verifier):
        generator.get_or_create_token("John Smith", EntityType.PERSON)
        generator.get_or_create_token("Acme Corp", EntityType.ORGANIZATION)
        mappings = generator.get_all_mappings()

        failures = verifier.verify_all_hmacs(mappings)
        assert failures == []

    def test_corrupted_hmac(self, generator, verifier):
        generator.get_or_create_token("John Smith", EntityType.PERSON)
        mappings = generator.get_all_mappings()

        # Corrupt an HMAC
        key = list(mappings.keys())[0]
        mapping = mappings[key]
        corrupted_token = Token(
            token_text=mapping.token.token_text,
            entity_type=mapping.token.entity_type,
            hmac_tag="corrupted_hmac_value",
        )
        mappings[key] = EntityMapping(
            token=corrupted_token,
            original_value=mapping.original_value,
            normalized_key=mapping.normalized_key,
            entity_type=mapping.entity_type,
            first_seen=mapping.first_seen,
            source_files=mapping.source_files,
        )

        failures = verifier.verify_all_hmacs(mappings)
        assert len(failures) == 1
        assert failures[0] == "[PERSON_00001]"


class TestScanForRemainingTokens:
    def test_no_remaining(self, verifier, tmp_path):
        f = tmp_path / "clean.csv"
        f.write_text("John Smith,jane@example.com,Acme Corp")

        remaining = verifier.scan_for_remaining_tokens(f, ["PERSON_00001"])
        assert remaining == []

    def test_finds_remaining(self, verifier, tmp_path):
        f = tmp_path / "dirty.csv"
        f.write_text("PERSON_00001,jane@example.com,ORG_00001")

        remaining = verifier.scan_for_remaining_tokens(
            f, ["PERSON_00001", "ORG_00001"]
        )
        assert "PERSON_00001" in remaining
        assert "ORG_00001" in remaining
