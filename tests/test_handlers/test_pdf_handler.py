"""Tests for the PDF input-only handler."""

from __future__ import annotations

import os

import pytest

from cowork_shield.exceptions import CoWorkShieldError, PdfInputOnlyError
from cowork_shield.extractors.pdf_markdown import PDFExtractionResult
from cowork_shield.handlers.pdf_handler import PdfHandler
from cowork_shield.models import DetectedEntity, EntityType
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


class FakeExtractor:
    def __init__(self, markdown: str = ""):
        self._markdown = markdown

    def extract(self, _):
        return PDFExtractionResult(markdown=self._markdown, backend="test")


class TestPdfHandler:
    def test_anonymize_pdf_to_markdown(self, tmp_path):
        handler = PdfHandler(extractor=FakeExtractor("John Smith john@example.com"))
        detection = FakeDetectionEngine()
        generator = TokenGenerator(os.urandom(32))

        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"%PDF-1.4\n")
        output_path = tmp_path / "output.md"

        records, file_record = handler.anonymize(
            input_path,
            output_path,
            detection,
            generator,
            source_file="input.pdf",
        )

        assert output_path.exists()
        assert "[PERSON_00001]" in output_path.read_text(encoding="utf-8")
        assert len(records) == 2
        assert file_record.format == "pdf->md"

    def test_anonymize_pdf_to_docx(self, tmp_path):
        handler = PdfHandler(
            pdf_output_format="docx",
            extractor=FakeExtractor("# Heading\n\nJohn Smith"),
        )
        detection = FakeDetectionEngine()
        generator = TokenGenerator(os.urandom(32))

        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"%PDF-1.4\n")
        output_path = tmp_path / "output.docx"

        _, file_record = handler.anonymize(
            input_path,
            output_path,
            detection,
            generator,
            source_file="input.pdf",
        )

        assert output_path.exists()
        assert file_record.format == "pdf->docx"

    def test_rejects_invalid_output_suffix(self, tmp_path):
        handler = PdfHandler(extractor=FakeExtractor("John Smith"))
        detection = FakeDetectionEngine()
        generator = TokenGenerator(os.urandom(32))

        input_path = tmp_path / "input.pdf"
        input_path.write_bytes(b"%PDF-1.4\n")
        output_path = tmp_path / "output.pdf"

        with pytest.raises(CoWorkShieldError, match="must be .md or .docx"):
            handler.anonymize(
                input_path,
                output_path,
                detection,
                generator,
                source_file="input.pdf",
            )

    def test_restore_pdf_raises_input_only_error(self, tmp_path):
        handler = PdfHandler(extractor=FakeExtractor("John Smith"))

        with pytest.raises(PdfInputOnlyError):
            handler.restore(tmp_path / "in.pdf", tmp_path / "out.pdf", {})
