"""Tests for UI-facing pipeline API helpers."""

from __future__ import annotations

from cowork_shield.pipeline import get_workspaces, render_entity_table
from cowork_shield.pipeline import ui_api
from cowork_shield.exceptions import IncompleteRestorationError


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
