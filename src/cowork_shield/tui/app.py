"""Textual terminal UI for CoWork Shield."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, DataTable, Footer, Header, Input, Select, Static

from cowork_shield.exceptions import CoWorkShieldError
from cowork_shield.pipeline import (
    anonymize_file,
    get_workspaces,
    preview_entities,
    restore_file,
    sanitize_ui_error,
)


class ConfirmRiskScreen(ModalScreen[bool]):
    """Modal confirmation screen for high-risk anonymize operations."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, prompt: str):
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="risk-modal"):
            yield Static("Confirm High-Risk Operation", id="risk-title")
            yield Static(self._prompt, id="risk-prompt")
            with Horizontal():
                yield Button("Cancel", id="cancel", variant="default")
                yield Button("Proceed", id="confirm", variant="error")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class CoWorkShieldApp(App[None]):
    """Terminal UI for workspace/file operations and entity attestation preview."""

    TITLE = "CoWork Shield"
    SUB_TITLE = "HANDOFF B Terminal UI"
    CSS = """
    Screen {
        layout: vertical;
    }
    #controls {
        padding: 1;
        height: auto;
    }
    #entities {
        height: 1fr;
        margin: 0 1;
    }
    #status {
        height: 3;
        padding: 0 1;
    }
    #risk-modal {
        width: 80%;
        height: auto;
        border: round $surface;
        background: $panel;
        padding: 1 2;
    }
    #risk-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #risk-prompt {
        margin-bottom: 1;
    }
    Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("p", "preview", "Preview"),
        Binding("a", "anonymize", "Anonymize"),
        Binding("r", "restore", "Restore"),
        Binding("w", "refresh_workspaces", "Refresh Workspaces"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical(id="controls"):
            yield Static("Workspace")
            yield Select(
                self._workspace_options(),
                value="default",
                id="workspace",
                allow_blank=False,
            )
            yield Input(placeholder="Path to file (CSV/XLSX/DOCX/TXT)", id="file_path")
            yield Static("Language")
            yield Select(
                [("Auto", "auto"), ("English", "en"), ("Hebrew", "he")],
                value="auto",
                id="language",
                allow_blank=False,
            )
            yield Checkbox("Allow lossy XLSX (--allow-lossy-xlsx)", id="allow_lossy_xlsx")
            yield Checkbox(
                "Force re-anonymize override (--force-reanonymize)",
                id="force_reanonymize",
            )
            yield Input(
                placeholder="Override reason (required if force re-anonymize is enabled)",
                id="override_reason",
            )
            with Horizontal():
                yield Button("Preview", id="preview", variant="default")
                yield Button("Anonymize", id="anonymize", variant="primary")
                yield Button("Restore", id="restore", variant="success")
                yield Button("Refresh Workspaces", id="refresh", variant="warning")
        yield DataTable(id="entities")
        yield Static("Ready.", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#entities", DataTable)
        table.add_columns("Type", "Text", "Start", "End", "Score")
        table.cursor_type = "row"

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id == "anonymize":
            await self.action_anonymize()
            return

        actions = {
            "preview": self.action_preview,
            "restore": self.action_restore,
            "refresh": self.action_refresh_workspaces,
        }
        handler = actions.get(button_id)
        if handler is not None:
            handler()

    def action_preview(self) -> None:
        path = self._selected_file()
        if path is None:
            return
        try:
            rows = preview_entities(path, language=self._selected_language())
            self._set_table_rows(rows)
            self._set_status(f"Previewed {len(rows)} entity rows from {path.name}.")
        except (CoWorkShieldError, OSError) as exc:
            code, message = sanitize_ui_error(exc)
            self._set_status(f"Preview failed [{code}]: {message}")

    async def action_anonymize(self) -> None:
        path = self._selected_file()
        if path is None:
            return
        workspace = self._selected_workspace()
        language = self._selected_language()
        allow_lossy_xlsx = self.query_one("#allow_lossy_xlsx", Checkbox).value
        force_reanonymize = self.query_one("#force_reanonymize", Checkbox).value
        override_reason = (self.query_one("#override_reason", Input).value or "").strip()

        if force_reanonymize and not override_reason:
            self._set_status("Force re-anonymize requires an override reason.")
            return

        if allow_lossy_xlsx or force_reanonymize:
            prompt_lines = ["This anonymize operation includes high-risk overrides:"]
            if allow_lossy_xlsx:
                prompt_lines.append("- Allow lossy XLSX processing is enabled.")
            if force_reanonymize:
                prompt_lines.append("- Force re-anonymize override is enabled.")
                prompt_lines.append(f"- Reason: {override_reason}")
            prompt_lines.append("Proceed?")
            confirmed = await self.push_screen_wait(ConfirmRiskScreen("\n".join(prompt_lines)))
            if not confirmed:
                self._set_status("Anonymize cancelled by user.")
                return

        try:
            result = anonymize_file(
                path,
                workspace,
                language=language,
                allow_lossy_xlsx=allow_lossy_xlsx,
                force_reanonymize=force_reanonymize,
                reason=override_reason,
            )
            self._set_table_rows(result.entity_rows)
            self._set_status(result.summary)
        except (CoWorkShieldError, OSError) as exc:
            code, message = sanitize_ui_error(exc)
            self._set_status(f"Anonymize failed [{code}]: {message}")

    def action_restore(self) -> None:
        path = self._selected_file()
        if path is None:
            return
        workspace = self._selected_workspace()
        try:
            result = restore_file(path, workspace)
            self._set_status(result.summary)
        except (CoWorkShieldError, OSError) as exc:
            code, message = sanitize_ui_error(exc)
            self._set_status(f"Restore failed [{code}]: {message}")

    def action_refresh_workspaces(self) -> None:
        select = self.query_one("#workspace", Select)
        select.set_options(self._workspace_options())
        current = self._selected_workspace()
        self._set_status(f"Workspace list refreshed. Current: {current}")

    def _selected_workspace(self) -> str:
        select = self.query_one("#workspace", Select)
        value = select.value
        if value in (None, Select.BLANK):
            return "default"
        return str(value)

    def _selected_file(self) -> Path | None:
        input_widget = self.query_one("#file_path", Input)
        raw = (input_widget.value or "").strip()
        if not raw:
            self._set_status("File path is required.")
            return None
        path = Path(raw).expanduser()
        if not path.exists():
            self._set_status(f"File not found: {path}")
            return None
        return path.resolve()

    def _selected_language(self) -> str:
        select = self.query_one("#language", Select)
        value = select.value
        if value in (None, Select.BLANK):
            return "auto"
        return str(value)

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _set_table_rows(self, rows: list[dict[str, str]]) -> None:
        table = self.query_one("#entities", DataTable)
        table.clear()
        for row in rows:
            table.add_row(
                row["type"],
                row["text"],
                row["start"],
                row["end"],
                row["score"],
            )

    @staticmethod
    def _workspace_options() -> list[tuple[str, str]]:
        return [(name, name) for name in get_workspaces()]


def run() -> None:
    """Console script entrypoint."""
    CoWorkShieldApp().run()


if __name__ == "__main__":
    run()
