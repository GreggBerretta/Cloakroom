"""Tests for Gradio UI guardrails and safe error messaging."""

from __future__ import annotations

from types import SimpleNamespace

from cowork_shield.exceptions import IncompleteRestorationError
from cowork_shield.ui import gradio_app


class TestGradioShieldGuardrails:
    def test_requires_reason_when_force_reanonymize_enabled(self):
        uploaded = SimpleNamespace(name="/tmp/fake.txt")
        output_file, _, status = gradio_app.shield(
            uploaded,
            "default",
            "auto",
            "md",
            [],
            False,
            False,
            True,
            "",
            True,
            False,
        )
        assert output_file is None
        assert "Reason is required" in status

    def test_requires_confirmation_for_risky_overrides(self):
        uploaded = SimpleNamespace(name="/tmp/fake.txt")
        output_file, _, status = gradio_app.shield(
            uploaded,
            "default",
            "auto",
            "md",
            [],
            False,
            True,
            False,
            "",
            False,
            False,
        )
        assert output_file is None
        assert "confirmation" in status.lower()

    def test_uses_sanitized_error_message(self, monkeypatch):
        uploaded = SimpleNamespace(name="/tmp/fake.txt")

        def _raise(*args, **kwargs):
            raise IncompleteRestorationError(["[PERSON_00001]"])

        monkeypatch.setattr(gradio_app, "anonymize_file", _raise)
        output_file, _, status = gradio_app.shield(
            uploaded,
            "default",
            "auto",
            "md",
            [],
            False,
            False,
            False,
            "",
            False,
            False,
        )
        assert output_file is None
        assert "IncompleteRestorationError" in status
        assert "PERSON_00001" not in status

    def test_requires_pdf_acknowledgement(self):
        uploaded = SimpleNamespace(name="/tmp/fake.pdf")
        output_file, _, status = gradio_app.shield(
            uploaded,
            "default",
            "auto",
            "md",
            [],
            False,
            False,
            False,
            "",
            False,
            False,
        )
        assert output_file is None
        assert "input-only" in status.lower()

    def test_refresh_column_dropdown_uses_pipeline_columns(self, monkeypatch):
        uploaded = SimpleNamespace(name="/tmp/fake.csv")

        monkeypatch.setattr(
            gradio_app,
            "get_file_columns",
            lambda _path: [
                {"label": "A: Name [text] (e.g. Alice)", "name": "Name"},
                {"label": "B: Deal ID [text] (e.g. DEAL-1)", "name": "Deal ID"},
            ],
        )

        dropdown = gradio_app._refresh_column_dropdown(uploaded)
        assert dropdown.choices == [
            ("A: Name [text] (e.g. Alice)", "Name"),
            ("B: Deal ID [text] (e.g. DEAL-1)", "Deal ID"),
        ]

    def test_launch_blocks_non_localhost(self):
        try:
            gradio_app.launch(["--server-name", "0.0.0.0"])
        except ValueError as exc:
            assert "127.0.0.1" in str(exc)
        else:
            raise AssertionError("Expected localhost enforcement error")
