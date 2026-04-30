"""Tests for the PDF -> markdown extractor backends."""

from __future__ import annotations

from pathlib import Path

import pytest

from cloakroom.exceptions import PdfExtractionError
from cloakroom.extractors.pdf_markdown import PDFExtractor


def _write_test_pdf(path: Path, *, pages: list[list[str]]) -> None:
    """Write a small PDF using reportlab. Each page is a list of text lines."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    page_width, page_height = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 12)
    for page_lines in pages:
        y = page_height - 48
        for line in page_lines:
            c.drawString(48, y, line)
            y -= 16
        c.showPage()
    c.save()


def _force_pdfplumber_backend(monkeypatch) -> None:
    """Skip docling so we exercise the pdfplumber fallback path."""
    def _raise(_path: Path):
        raise ImportError("docling skipped for test")

    monkeypatch.setattr(
        "cloakroom.extractors.pdf_markdown.PDFExtractor._extract_with_docling",
        staticmethod(_raise),
    )


def test_pdfplumber_backend_extracts_text(tmp_path, monkeypatch):
    _force_pdfplumber_backend(monkeypatch)
    pdf_path = tmp_path / "one.pdf"
    _write_test_pdf(
        pdf_path,
        pages=[
            ["Sarah Morgan emailed sarah.morgan@acmehealth.eu",
             "about the Project Lantern renewal."],
        ],
    )
    result = PDFExtractor().extract(pdf_path)
    assert result.backend == "pdfplumber"
    assert "Sarah Morgan" in result.markdown
    assert "Project Lantern" in result.markdown
    assert result.markdown.startswith("## Page 1")


def test_pdfplumber_backend_includes_per_page_headers(tmp_path, monkeypatch):
    _force_pdfplumber_backend(monkeypatch)
    pdf_path = tmp_path / "multi.pdf"
    _write_test_pdf(
        pdf_path,
        pages=[
            ["Page one body content."],
            ["Page two body content."],
        ],
    )
    result = PDFExtractor().extract(pdf_path)
    assert "## Page 1" in result.markdown
    assert "## Page 2" in result.markdown
    assert "Page one body content" in result.markdown
    assert "Page two body content" in result.markdown


def test_pdfplumber_backend_raises_on_empty_pdf(tmp_path, monkeypatch):
    _force_pdfplumber_backend(monkeypatch)
    pdf_path = tmp_path / "empty.pdf"
    _write_test_pdf(pdf_path, pages=[[]])
    with pytest.raises(PdfExtractionError):
        PDFExtractor().extract(pdf_path)
