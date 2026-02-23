"""Tests for the CLI interface."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from cowork_shield.cli import main
from cowork_shield import cli as cli_module
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

    def test_workspace_verify_security_help(self, runner):
        result = runner.invoke(main, ["workspace", "verify-security", "--help"])
        assert result.exit_code == 0

    def test_onboarding_help(self, runner):
        result = runner.invoke(main, ["onboarding", "--help"])
        assert result.exit_code == 0
        assert "--export-key" in result.output

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

    def test_workspace_verify_security_pass(self, runner, tmp_path, monkeypatch):
        vault = tmp_path / "vault.enc"
        vault.write_bytes(b"x")
        os.chmod(vault, 0o600)

        class FakeWorkspaceManager:
            def list_workspaces(self):
                return [{"name": "default"}]

            def get_workspace_metadata(self, name):
                assert name == "default"
                return {"vault_path": str(vault)}

        monkeypatch.setattr(cli_module, "WorkspaceManager", FakeWorkspaceManager)
        monkeypatch.setattr(cli_module, "verify_keychain_permissions", lambda: (True, "ok"))

        result = runner.invoke(main, ["workspace", "verify-security"])
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_onboarding_reminder_prints_when_incomplete(self, runner, tmp_path, monkeypatch):
        marker = tmp_path / ".onboarding_complete"
        monkeypatch.setattr(cli_module, "ONBOARDING_MARKER", marker)
        result = runner.invoke(main, ["logs", "--help"])
        assert result.exit_code == 0
        assert "First-run onboarding is not complete" in result.output

    def test_pdf_runtime_warning_before_processing(self, runner, tmp_path, monkeypatch):
        pdf_path = tmp_path / "sample.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%test\n")
        marker = tmp_path / ".onboarding_complete"
        marker.write_text("ok", encoding="utf-8")
        monkeypatch.setattr(cli_module, "ONBOARDING_MARKER", marker)

        class FakeWorkspaceManager:
            def get_workspace_metadata(self, _name):
                return {"workspace_id": "ws-1"}

            def get_or_create_workspace(self, _name, ttl_hours=168):
                return SimpleNamespace(workspace_id="ws-1", workspace_name="default")

        class FakePipeline:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, input_path, output_path):
                out = output_path or input_path.with_suffix(".anonymized.md")
                out.write_text("tokenized", encoding="utf-8")
                return SimpleNamespace(
                    input_path=input_path,
                    output_path=out,
                    workspace_name="default",
                    entities_found=0,
                    tokens_applied=0,
                    backup_path=None,
                )

        monkeypatch.setattr(cli_module, "WorkspaceManager", FakeWorkspaceManager)
        monkeypatch.setattr(cli_module, "AnonymizePipeline", FakePipeline)

        result = runner.invoke(main, ["anonymize", str(pdf_path), "-w", "default"])
        assert result.exit_code == 0
        assert "PDF input warning" in result.output
