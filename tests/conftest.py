"""Shared test fixtures for Cloakroom."""

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture
def tmp_workspace(tmp_path):
    """Provide a temporary workspace directory for tests."""
    ws_dir = tmp_path / "workspaces" / "test-workspace"
    ws_dir.mkdir(parents=True)
    return ws_dir
