"""Textual terminal UI for CoWork Shield."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Header, Input, Select, Static

from cowork_shield.exceptions import CoWorkShieldError
from cowork_shield.pipeline import anonymize_file, get_workspaces, preview_entities, restore_file


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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "preview": self.action_preview,
            "anonymize": self.action_anonymize,
            "restore": self.action_restore,
            "refresh": self.action_refresh_workspaces,
        }
        handler = actions.get(event.button.id or "")
        if handler is not None:
            handler()

    def action_preview(self) -> None:
        path = self._selected_file()
        if path is None:
            return
        try:
            rows = preview_entities(path)
            self._set_table_rows(rows)
            self._set_status(f"Previewed {len(rows)} entity rows from {path.name}.")
        except (CoWorkShieldError, OSError) as exc:
            self._set_status(f"Preview failed [{exc.__class__.__name__}]: {exc}")

    def action_anonymize(self) -> None:
        path = self._selected_file()
        if path is None:
            return
        workspace = self._selected_workspace()
        try:
            result = anonymize_file(path, workspace)
            self._set_table_rows(result.entity_rows)
            self._set_status(result.summary)
        except (CoWorkShieldError, OSError) as exc:
            self._set_status(f"Anonymize failed [{exc.__class__.__name__}]: {exc}")

    def action_restore(self) -> None:
        path = self._selected_file()
        if path is None:
            return
        workspace = self._selected_workspace()
        try:
            result = restore_file(path, workspace)
            self._set_status(result.summary)
        except (CoWorkShieldError, OSError) as exc:
            self._set_status(f"Restore failed [{exc.__class__.__name__}]: {exc}")

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

