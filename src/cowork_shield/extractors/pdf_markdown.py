"""PDF to Markdown extraction helpers for the input-only PDF pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cowork_shield.exceptions import PdfExtractionError


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
            return self._extract_with_pymupdf(input_path)
        except ImportError:
            errors.append("PyMuPDF not installed")
        except Exception as exc:  # pragma: no cover - backend-specific failures
            errors.append(f"PyMuPDF failed ({exc.__class__.__name__})")

        detail = "; ".join(errors) if errors else "no extractor available"
        raise PdfExtractionError(
            "PDF extraction failed. Install docling or pymupdf and retry. "
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
    def _extract_with_pymupdf(input_path: Path) -> PDFExtractionResult:
        import fitz

        page_sections: list[str] = []
        with fitz.open(str(input_path)) as doc:
            for idx, page in enumerate(doc):
                page_text = page.get_text("text").strip()
                if not page_text:
                    continue
                page_sections.append(f"## Page {idx + 1}\n\n{page_text}")

        markdown = "\n\n".join(page_sections).strip()
        if not markdown:
            raise PdfExtractionError("PyMuPDF extracted empty markdown from PDF.")

        return PDFExtractionResult(markdown=markdown, backend="pymupdf")


def extract_pdf_to_markdown(input_path: Path) -> str:
    """Extract markdown text from a PDF input path."""
    return PDFExtractor().extract(input_path).markdown
