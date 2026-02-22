"""Anonymization pipeline orchestration."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.exceptions import UnsupportedFormatError
from cowork_shield.handlers.csv_handler import CsvHandler
from cowork_shield.handlers.docx import DocxHandler
from cowork_shield.handlers.xlsx import XlsxHandler
from cowork_shield.models import ReplacementRecord
from cowork_shield.workspace.manager import WorkspaceContext

HANDLER_MAP = {
    ".xlsx": XlsxHandler,
    ".csv": CsvHandler,
    ".docx": DocxHandler,
}


@dataclass
class AnonymizeResult:
    """Summary of an anonymization operation."""

    input_path: Path
    output_path: Path
    backup_path: Path | None
    entities_found: int
    tokens_applied: int
    workspace_name: str


class AnonymizePipeline:
    """Orchestrates the full anonymization flow for a file.

    Flow:
    1. Resolve file handler based on extension
    2. Create backup of original file
    3. Run handler.anonymize() (detection + replacement)
    4. Store all new mappings in vault
    5. Record file metadata in vault
    6. Persist vault to disk (atomic write)
    """

    def __init__(
        self,
        workspace_ctx: WorkspaceContext,
        score_threshold: float = 0.7,
    ):
        self._ctx = workspace_ctx
        self._detection = DetectionEngine(score_threshold=score_threshold)

    def run(
        self,
        input_path: Path,
        output_path: Path | None = None,
    ) -> AnonymizeResult:
        """Anonymize a single file within the workspace context."""
        input_path = input_path.resolve()

        # 1. Validate format
        suffix = input_path.suffix.lower()
        handler_cls = HANDLER_MAP.get(suffix)
        if handler_cls is None:
            raise UnsupportedFormatError(suffix)
        handler = handler_cls()

        # 2. Set default output path
        if output_path is None:
            output_path = input_path.with_stem(input_path.stem + ".anonymized")

        # 3. Create backup
        backup_path = None
        if suffix == ".xlsx":
            backup_path = input_path.with_suffix(input_path.suffix + ".backup")
            if not backup_path.exists():
                shutil.copy2(input_path, backup_path)

        # 4. Run anonymization
        records, file_record = handler.anonymize(
            input_path,
            output_path,
            self._detection,
            self._ctx.token_generator,
            source_file=input_path.name,
        )

        # 5. Update vault with new mappings from the generator
        counters, mappings = self._ctx.token_generator.export_state()
        self._ctx.vault_data.token_counter = counters
        self._ctx.vault_data.mappings = mappings

        # 6. Record file in vault
        self._ctx.vault_data.file_records.append(file_record)

        # 7. Persist vault
        self._ctx.persist()

        return AnonymizeResult(
            input_path=input_path,
            output_path=output_path,
            backup_path=backup_path,
            entities_found=file_record.entities_found,
            tokens_applied=file_record.tokens_applied,
            workspace_name=self._ctx.workspace_name,
        )
