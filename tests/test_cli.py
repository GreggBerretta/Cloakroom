"""Tests for the CLI interface."""

import pytest
from click.testing import CliRunner

from cowork_shield.cli import main


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

    def test_restore_help(self, runner):
        result = runner.invoke(main, ["restore", "--help"])
        assert result.exit_code == 0
        assert "--workspace" in result.output

    def test_workspace_list_help(self, runner):
        result = runner.invoke(main, ["workspace", "list", "--help"])
        assert result.exit_code == 0

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

    def test_anonymize_nonexistent_file(self, runner):
        result = runner.invoke(main, ["anonymize", "/nonexistent/file.csv"])
        assert result.exit_code != 0
