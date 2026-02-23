"""Tests for the CLI interface."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from cowork_shield.cli import main
from cowork_shield.logging import config as log_config

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def runner():
    return CliRunner()


class TestCli:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "anonymize" in result.output
        assert "inspect-columns" in result.output
        assert "ipc-server" in result.output
        assert "ipc-stdio" in result.output
        assert "logs" in result.output
        assert "restore" in result.output
        assert "shield-clipboard" in result.output
        assert "restore-clipboard" in result.output
        assert "workspace" in result.output

    def test_anonymize_help(self, runner):
        result = runner.invoke(main, ["anonymize", "--help"])
        assert result.exit_code == 0
        assert "--workspace" in result.output
        assert "--ttl" in result.output
        assert "--score-threshold" in result.output
        assert "--columns" in result.output
        assert "--detect-pii" in result.output

    def test_restore_help(self, runner):
        result = runner.invoke(main, ["restore", "--help"])
        assert result.exit_code == 0
        assert "--workspace" in result.output

    def test_workspace_list_help(self, runner):
        result = runner.invoke(main, ["workspace", "list", "--help"])
        assert result.exit_code == 0

    def test_logs_help(self, runner):
        result = runner.invoke(main, ["logs", "--help"])
        assert result.exit_code == 0
        assert "export" in result.output
        assert "delete" in result.output

    def test_workspace_export_key_help(self, runner):
        result = runner.invoke(main, ["workspace", "export-key", "--help"])
        assert result.exit_code == 0
        assert "--workspace" in result.output
        assert "--output" in result.output

    def test_workspace_import_key_help(self, runner):
        result = runner.invoke(main, ["workspace", "import-key", "--help"])
        assert result.exit_code == 0
        assert "--workspace" in result.output
        assert "--input" in result.output

    def test_shield_clipboard_help(self, runner):
        result = runner.invoke(main, ["shield-clipboard", "--help"])
        assert result.exit_code == 0
        assert "--workspace" in result.output

    def test_restore_clipboard_help(self, runner):
        result = runner.invoke(main, ["restore-clipboard", "--help"])
        assert result.exit_code == 0
        assert "--workspace" in result.output

    def test_ipc_server_help(self, runner):
        result = runner.invoke(main, ["ipc-server", "--help"])
        assert result.exit_code == 0
        assert "--socket-path" in result.output

    def test_ipc_stdio_help(self, runner):
        result = runner.invoke(main, ["ipc-stdio", "--help"])
        assert result.exit_code == 0

    def test_inspect_columns(self, runner):
        result = runner.invoke(main, ["inspect-columns", str(FIXTURES_DIR / "sample_data.csv")])
        assert result.exit_code == 0
        assert "Columns: sample_data.csv" in result.output
        assert "A" in result.output
        assert "Name" in result.output

    def test_anonymize_nonexistent_file(self, runner):
        result = runner.invoke(main, ["anonymize", "/nonexistent/file.csv"])
        assert result.exit_code != 0

    def test_logs_export_and_delete(self, runner, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(log_config, "LOG_DIR", log_dir)
        monkeypatch.setattr(log_config, "LOG_FILE", log_dir / "cowork_shield.log")
        monkeypatch.setattr(log_config, "LOG_KEY_FILE", log_dir / ".logkey")

        export_path = tmp_path / "support-export.json"
        result = runner.invoke(
            main,
            [
                "--verbose",
                "logs",
                "export",
                "--no-include-audit",
                "--output",
                str(export_path),
            ],
        )
        assert result.exit_code == 0
        assert export_path.exists()
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        assert payload["include_app"] is True
        assert payload["include_audit"] is False

        delete_result = runner.invoke(main, ["logs", "delete", "--yes"])
        assert delete_result.exit_code == 0
        assert "Log cleanup complete" in delete_result.output
