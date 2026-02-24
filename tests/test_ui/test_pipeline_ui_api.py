"""Tests for UI-facing pipeline API helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cowork_shield.pipeline import get_workspaces, render_entity_table
from cowork_shield.pipeline import ui_api
from cowork_shield.exceptions import IncompleteRestorationError

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestUIAPIHelpers:
    def test_render_entity_table_empty(self):
        html = render_entity_table([])
        assert "No entities detected" in html

    def test_render_entity_table_rows(self):
        html = render_entity_table(
            [
                {
                    "type": "PERSON",
                    "text": "John Smith",
                    "start": "0",
                    "end": "10",
                    "score": "0.987",
                }
            ]
        )
        assert "<table" in html
        assert "John Smith" in html
        assert "PERSON" in html

    def test_get_workspaces_includes_default(self, monkeypatch):
        class FakeWorkspaceManager:
            def list_workspaces(self):
                return [{"name": "client-a"}, {"name": "client-b"}]

        monkeypatch.setattr(ui_api, "WorkspaceManager", FakeWorkspaceManager)
        names = get_workspaces()
        assert "default" in names
        assert "client-a" in names

    def test_sanitize_ui_error_strips_sensitive_details(self):
        code, message = ui_api.sanitize_ui_error(
            IncompleteRestorationError(["[PERSON_00001]", "[EMAIL_00002]"])
        )
        assert code == "IncompleteRestorationError"
        assert "PERSON_00001" not in message
        assert "EMAIL_00002" not in message

    def test_sanitize_ui_error_fallback_message_does_not_echo_input(self):
        code, message = ui_api.sanitize_ui_error(RuntimeError("secret payload 123"))
        assert code == "RuntimeError"
        assert "secret payload 123" not in message

    def test_preview_entities_reads_markdown(self, monkeypatch, tmp_path):
        md_path = tmp_path / "notes.md"
        md_path.write_text("# Header\n\nJohn Smith", encoding="utf-8")

        class FakeDetectionEngine:
            def __init__(self, score_threshold):
                self._score_threshold = score_threshold

            def detect(self, text, language="auto"):
                assert "John Smith" in text
                return [
                    SimpleNamespace(
                        entity_type=SimpleNamespace(value="PERSON"),
                        text="John Smith",
                        start=10,
                        end=20,
                        score=0.99,
                    )
                ]

        monkeypatch.setattr(ui_api, "DetectionEngine", FakeDetectionEngine)

        rows = ui_api.preview_entities(md_path, language="en")
        assert len(rows) == 1
        assert rows[0]["type"] == "PERSON"
        assert rows[0]["text"] == "John Smith"

    def test_get_file_columns_csv(self):
        columns = ui_api.get_file_columns(FIXTURES_DIR / "sample_data.csv")
        assert len(columns) == 5
        assert columns[0]["letter"] == "A"
        assert columns[0]["name"] == "Name"
        assert columns[0]["data_type"] == "text"
        assert columns[0]["sample"]

    def test_anonymize_file_column_only_skips_preview(self, monkeypatch, tmp_path):
        preview_called = {"value": False}

        class FakeWorkspaceManager:
            def get_workspace_metadata(self, _workspace):
                return {"workspace_id": "existing"}

            def get_or_create_workspace(self, workspace, ttl_hours=168):
                return SimpleNamespace(workspace_name=workspace)

        class FakePipeline:
            def __init__(self, *args, **kwargs):
                assert kwargs["selected_columns"] == ["Name"]
                assert kwargs["detect_pii"] is False

            def run(self, input_path, out_path):
                output = out_path or input_path.with_name(input_path.stem + ".anonymized.csv")
                output.write_text("ok", encoding="utf-8")
                return SimpleNamespace(
                    input_path=input_path,
                    output_path=output,
                    entities_found=0,
                    tokens_applied=1,
                )

        def fake_preview(*args, **kwargs):
            preview_called["value"] = True
            return []

        monkeypatch.setattr(ui_api, "WorkspaceManager", FakeWorkspaceManager)
        monkeypatch.setattr(ui_api, "AnonymizePipeline", FakePipeline)
        monkeypatch.setattr(ui_api, "preview_entities", fake_preview)

        input_path = tmp_path / "sheet.csv"
        input_path.write_text("Name\nAlice\n", encoding="utf-8")
        result = ui_api.anonymize_file(
            input_path,
            "default",
            columns=["Name"],
            detect_pii=False,
            license_key="pro_1234567890ABCDEF",
        )

        assert preview_called["value"] is False
        assert "Detection: column-only" in result.summary

    def test_anonymize_file_new_workspace_adds_recovery_warning(self, monkeypatch, tmp_path):
        class FakeWorkspaceManager:
            def get_workspace_metadata(self, _workspace):
                raise ui_api.WorkspaceNotFoundError("default")

            def get_or_create_workspace(self, workspace, ttl_hours=168):
                return SimpleNamespace(workspace_name=workspace)

        class FakePipeline:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, input_path, out_path):
                output = out_path or input_path.with_name(input_path.stem + ".anonymized.csv")
                output.write_text("ok", encoding="utf-8")
                return SimpleNamespace(
                    input_path=input_path,
                    output_path=output,
                    entities_found=1,
                    tokens_applied=1,
                )

        monkeypatch.setattr(ui_api, "WorkspaceManager", FakeWorkspaceManager)
        monkeypatch.setattr(ui_api, "AnonymizePipeline", FakePipeline)
        monkeypatch.setattr(ui_api, "preview_entities", lambda *args, **kwargs: [])

        input_path = tmp_path / "sheet.csv"
        input_path.write_text("Name\nAlice\n", encoding="utf-8")
        result = ui_api.anonymize_file(input_path, "default")
        assert "Export recovery key" in result.summary
