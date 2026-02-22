"""Tests for the CLI interface."""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cowork_shield.cli import main

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
        assert "restore" in result.output
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

    def test_anonymize_nonexistent_file(self, runner):
        result = runner.invoke(main, ["anonymize", "/nonexistent/file.csv"])
        assert result.exit_code != 0
