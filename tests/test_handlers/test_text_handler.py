"""Tests for the plain text handler."""

import os

from cowork_shield.models import DetectedEntity, EntityType
from cowork_shield.handlers.text_handler import TextHandler
from cowork_shield.tokenizer.generator import TokenGenerator


class FakeDetectionEngine:
    def detect_in_cell(self, text: str, source_id: str):
        entities = []
        if "John Smith" in text:
            start = text.index("John Smith")
            entities.append(
                DetectedEntity(
                    entity_type=EntityType.PERSON,
                    text="John Smith",
                    start=start,
                    end=start + len("John Smith"),
                    score=0.99,
                    source_id=source_id,
                )
            )
        if "john@example.com" in text:
            start = text.index("john@example.com")
            entities.append(
                DetectedEntity(
                    entity_type=EntityType.EMAIL,
                    text="john@example.com",
                    start=start,
                    end=start + len("john@example.com"),
                    score=0.99,
                    source_id=source_id,
                )
            )
        return entities


class TestTextHandler:
    def test_round_trip(self, tmp_path):
        handler = TextHandler()
        detection = FakeDetectionEngine()
        generator = TokenGenerator(os.urandom(32))

        input_path = tmp_path / "notes.txt"
        input_path.write_text(
            "John Smith can be reached at john@example.com",
            encoding="utf-8",
        )
        anon_path = tmp_path / "notes.anonymized.txt"
        restored_path = tmp_path / "notes.restored.txt"

        records, file_record = handler.anonymize(
            input_path,
            anon_path,
            detection,
            generator,
            source_file="notes.txt",
        )

        assert anon_path.exists()
        assert file_record.format == "txt"
        assert file_record.entities_found == 2
        assert file_record.tokens_applied == 2
        assert len(records) == 2
        assert "[PERSON_00001]" in anon_path.read_text(encoding="utf-8")

        handler.restore(anon_path, restored_path, generator.get_reverse_lookup())
        assert restored_path.read_text(encoding="utf-8") == input_path.read_text(encoding="utf-8")

    def test_no_entities(self, tmp_path):
        handler = TextHandler()
        detection = FakeDetectionEngine()
        generator = TokenGenerator(os.urandom(32))

        input_path = tmp_path / "plain.txt"
        input_path.write_text("no pii here", encoding="utf-8")
        anon_path = tmp_path / "plain.anonymized.txt"

        records, file_record = handler.anonymize(
            input_path,
            anon_path,
            detection,
            generator,
            source_file="plain.txt",
        )

        assert records == []
        assert file_record.entities_found == 0
        assert anon_path.read_text(encoding="utf-8") == "no pii here"

    def test_large_text(self, tmp_path):
        handler = TextHandler()
        detection = FakeDetectionEngine()
        generator = TokenGenerator(os.urandom(32))

        large_text = ("John Smith sent john@example.com.\n" * 4000).strip()
        input_path = tmp_path / "large.txt"
        input_path.write_text(large_text, encoding="utf-8")
        anon_path = tmp_path / "large.anonymized.txt"

        _, file_record = handler.anonymize(
            input_path,
            anon_path,
            detection,
            generator,
            source_file="large.txt",
        )

        assert file_record.entities_found == 2
        anonymized = anon_path.read_text(encoding="utf-8")
        assert "[PERSON_00001]" in anonymized
        assert "[EMAIL_00001]" in anonymized
