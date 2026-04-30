"""PDF to Markdown extraction helpers for the input-only PDF pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cloakroom.exceptions import PdfExtractionError


@dataclass(frozen=True)
class PDFExtractionResult:
    """Result of extracting a PDF into markdown text."""

    markdown: str
    backend: str


class PDFExtractor:
    """Extract PDF content into markdown with Docling-first strategy."""

    def extract(self, input_path: Path) -> PDFExtractionResult:
        input_path = input_path.expanduser().resolve()
        errors: list[str] = []

        try:
            return self._extract_with_docling(input_path)
        except ImportError:
            errors.append("docling not installed")
        except Exception as exc:  # pragma: no cover - backend-specific failures
            errors.append(f"docling failed ({exc.__class__.__name__})")

        try:
            return self._extract_with_pdfplumber(input_path)
        except ImportError:
            errors.append("pdfplumber not installed")
        except Exception as exc:  # pragma: no cover - backend-specific failures
            errors.append(f"pdfplumber failed ({exc.__class__.__name__})")

        detail = "; ".join(errors) if errors else "no extractor available"
        raise PdfExtractionError(
            "PDF extraction failed. Install docling or pdfplumber and retry. "
            f"Details: {detail}."
        )

    @staticmethod
    def _extract_with_docling(input_path: Path) -> PDFExtractionResult:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(str(input_path))
        document = getattr(result, "document", result)

        export = getattr(document, "export_to_markdown", None)
        if export is None:
            export = getattr(result, "export_to_markdown", None)

        if export is None:
            raise PdfExtractionError("Docling did not return a markdown exporter.")

        markdown = str(export()).strip()
        if not markdown:
            raise PdfExtractionError("Docling extracted empty markdown from PDF.")

        return PDFExtractionResult(markdown=markdown, backend="docling")

    @staticmethod
    def _extract_with_pdfplumber(input_path: Path) -> PDFExtractionResult:
        import pdfplumber

        page_sections: list[str] = []
        with pdfplumber.open(str(input_path)) as pdf:
            for idx, page in enumerate(pdf.pages):
                page_text = (page.extract_text() or "").strip()
                if not page_text:
                    continue
                page_sections.append(f"## Page {idx + 1}\n\n{page_text}")

        markdown = "\n\n".join(page_sections).strip()
        if not markdown:
            raise PdfExtractionError("pdfplumber extracted empty markdown from PDF.")

        return PDFExtractionResult(markdown=markdown, backend="pdfplumber")


def extract_pdf_to_markdown(input_path: Path) -> str:
    """Extract markdown text from a PDF input path."""
    return PDFExtractor().extract(input_path).markdown
