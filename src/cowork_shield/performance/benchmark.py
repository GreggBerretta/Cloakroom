"""Performance benchmark helpers for launch-readiness gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter
from typing import Any

from cowork_shield.clipboard.operations import restore_clipboard, shield_clipboard
from cowork_shield.pipeline.anonymize import AnonymizePipeline
from cowork_shield.pipeline.restore import RestorePipeline
from cowork_shield.workspace.manager import WorkspaceContext


@dataclass(frozen=True)
class BenchmarkResult:
    rows: int
    language: str
    anonymize_seconds: float
    restore_seconds: float
    clipboard_shield_seconds: float
    clipboard_restore_seconds: float
    captured_at: str
    workspace_name: str
    csv_input_path: str
    csv_anonymized_path: str
    csv_restored_path: str

    @property
    def clipboard_roundtrip_seconds(self) -> float:
        return self.clipboard_shield_seconds + self.clipboard_restore_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "captured_at": self.captured_at,
            "rows": self.rows,
            "language": self.language,
            "workspace_name": self.workspace_name,
            "csv_input_path": self.csv_input_path,
            "csv_anonymized_path": self.csv_anonymized_path,
            "csv_restored_path": self.csv_restored_path,
            "anonymize_seconds": round(self.anonymize_seconds, 4),
            "restore_seconds": round(self.restore_seconds, 4),
            "clipboard_shield_seconds": round(self.clipboard_shield_seconds, 4),
            "clipboard_restore_seconds": round(self.clipboard_restore_seconds, 4),
            "clipboard_roundtrip_seconds": round(self.clipboard_roundtrip_seconds, 4),
        }


def run_csv_clipboard_benchmark(
    workspace_ctx: WorkspaceContext,
    *,
    rows: int = 10_000,
    language: str = "en",
) -> BenchmarkResult:
    """Run the launch readiness benchmark for CSV + clipboard flows."""
    normalized_language = (language or "en").strip().lower()
    with tempfile.TemporaryDirectory(prefix="cowork-shield-perf-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        csv_path = tmp_path / f"perf_{normalized_language}_{rows}.csv"
        csv_anonymized_path = csv_path.with_name(csv_path.stem + ".anonymized.csv")
        csv_restored_path = csv_path.with_name(csv_path.stem + ".restored.csv")

        _write_benchmark_csv(csv_path, rows=rows, language=normalized_language)

        anonymize_pipeline = AnonymizePipeline(
            workspace_ctx,
            score_threshold=0.7,
            language=normalized_language,
        )
        restore_pipeline = RestorePipeline(workspace_ctx)

        t0 = perf_counter()
        anonymize_pipeline.run(csv_path, csv_anonymized_path)
        anonymize_seconds = perf_counter() - t0

        t1 = perf_counter()
        restore_pipeline.run(csv_anonymized_path, csv_restored_path)
        restore_seconds = perf_counter() - t1

        sample_clipboard = _benchmark_clipboard_sample(normalized_language)
        _set_system_clipboard(sample_clipboard)
        t2 = perf_counter()
        shield_clipboard(workspace_ctx, score_threshold=0.7, language=normalized_language)
        clipboard_shield_seconds = perf_counter() - t2

        t3 = perf_counter()
        restore_clipboard(workspace_ctx)
        clipboard_restore_seconds = perf_counter() - t3

        return BenchmarkResult(
            rows=rows,
            language=normalized_language,
            anonymize_seconds=anonymize_seconds,
            restore_seconds=restore_seconds,
            clipboard_shield_seconds=clipboard_shield_seconds,
            clipboard_restore_seconds=clipboard_restore_seconds,
            captured_at=datetime.now(timezone.utc).isoformat(),
            workspace_name=workspace_ctx.workspace_name,
            csv_input_path=str(csv_path),
            csv_anonymized_path=str(csv_anonymized_path),
            csv_restored_path=str(csv_restored_path),
        )


def write_benchmark_result_json(result: BenchmarkResult, *, output_path: Path) -> Path:
    resolved = output_path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return resolved


def _write_benchmark_csv(path: Path, *, rows: int, language: str) -> None:
    if language == "he":
        header = "name,email,company,phone,notes\n"
        row_template = (
            "משה לוי {i},moshe{i}@example.com,חברת בדיקה {i},050-1234{i:04d},"
            "פגישת לקוח עם ישראל כהן {i}\n"
        )
    else:
        header = "name,email,company,phone,notes\n"
        row_template = (
            "John Smith {i},john{i}@example.com,Acme Corp {i},212-555-{i:04d},"
            "Client follow-up with Jane Doe {i}\n"
        )

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(header)
        for idx in range(rows):
            handle.write(row_template.format(i=idx))


def _benchmark_clipboard_sample(language: str) -> str:
    if language == "he":
        return "שלום, שמי משה לוי והטלפון שלי הוא 050-1234567 והמייל moshe@example.com"
    return "Hello, my name is John Smith. Email me at john.smith@example.com or call 212-555-1234."


def _set_system_clipboard(text: str) -> None:
    subprocess.run(
        ["pbcopy"],
        check=True,
        input=text,
        text=True,
        capture_output=True,
    )
