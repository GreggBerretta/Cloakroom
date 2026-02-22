"""Abstract FileHandler protocol for format-specific file processing."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.models import FileRecord, ReplacementRecord
from cowork_shield.tokenizer.generator import TokenGenerator


class FileHandler(Protocol):
    """Protocol for format-specific file processing.

    Each handler knows how to:
    1. Read a file and detect PII, replacing with tokens
    2. Read an anonymized file and restore original values
    """

    @staticmethod
    def can_handle(file_path: Path) -> bool:
        """Check if this handler supports the given file extension."""
        ...

    def anonymize(
        self,
        input_path: Path,
        output_path: Path,
        detection_engine: DetectionEngine,
        token_generator: TokenGenerator,
        source_file: str,
        language: str = "auto",
        selected_columns: list[str] | None = None,
        detect_pii: bool = True,
    ) -> tuple[list[ReplacementRecord], FileRecord]:
        """Anonymize a file. Returns replacement records and file metadata."""
        ...

    def restore(
        self,
        input_path: Path,
        output_path: Path,
        reverse_lookup: dict[str, str],
    ) -> None:
        """Restore an anonymized file to its original form."""
        ...
