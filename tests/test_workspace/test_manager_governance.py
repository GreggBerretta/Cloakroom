"""Workspace governance tests: close/recover/purge backup behaviors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cowork_shield.models import EntityType
from cowork_shield.workspace import manager as manager_mod
from cowork_shield.workspace.manager import WorkspaceManager


@pytest.fixture
def isolated_workspace_manager(tmp_path, monkeypatch):
    key_store: dict[str, bytes] = {}

    def fake_store(workspace_id: str, key: bytes) -> None:
        key_store[workspace_id] = key

    def fake_get(workspace_id: str) -> bytes | None:
        return key_store.get(workspace_id)

    def fake_delete(workspace_id: str) -> None:
        key_store.pop(workspace_id, None)

    monkeypatch.setattr(manager_mod, "store_master_key", fake_store)
    monkeypatch.setattr(manager_mod, "get_master_key", fake_get)
    monkeypatch.setattr(manager_mod, "delete_master_key", fake_delete)
    monkeypatch.setattr(manager_mod, "BACKUP_BASE_DIR", tmp_path / "backups")

    workspace_base = tmp_path / "workspaces"
    manager = WorkspaceManager(base_dir=workspace_base)
    return manager


def test_workspace_close_creates_encrypted_backup(isolated_workspace_manager: WorkspaceManager):
    ctx = isolated_workspace_manager.create_workspace("alpha", ttl_hours=24)
    backup_path = isolated_workspace_manager.close_workspace("alpha")

    assert backup_path.exists()
    assert backup_path.suffix == ".enc"
    assert str(backup_path).endswith(".enc")

    manifest_path = backup_path.with_suffix(".json")
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["workspace_id"] == ctx.workspace_id
    assert manifest["workspace_name"] == "alpha"


def test_workspace_recover_restores_prior_vault_snapshot(isolated_workspace_manager: WorkspaceManager):
    ctx = isolated_workspace_manager.create_workspace("beta", ttl_hours=24)
    ctx.token_generator.get_or_create_token("John Smith", EntityType.PERSON, source_file="f1.txt")
    ctx.persist()
    backup_path = isolated_workspace_manager.close_workspace("beta")

    # Mutate state after backup.
    ctx_after = isolated_workspace_manager.get_active_workspace("beta")
    ctx_after.token_generator.get_or_create_token("Acme Corp", EntityType.ORGANIZATION, source_file="f2.txt")
    ctx_after.persist()
    assert len(ctx_after.vault_data.mappings) >= 2

    recovered = isolated_workspace_manager.recover_workspace("beta", backup_path)
    assert len(recovered.vault_data.mappings) == 1
    only_mapping = next(iter(recovered.vault_data.mappings.values()))
    assert only_mapping.original_value == "John Smith"


def test_workspace_purge_clears_mappings_with_mandatory_backup(
    isolated_workspace_manager: WorkspaceManager,
):
    ctx = isolated_workspace_manager.create_workspace("gamma", ttl_hours=24)
    ctx.token_generator.get_or_create_token("Jane Doe", EntityType.PERSON, source_file="f3.txt")
    ctx.persist()
    assert len(ctx.vault_data.mappings) == 1

    backup_path = isolated_workspace_manager.purge_workspace("gamma")
    assert Path(backup_path).exists()

    reloaded = isolated_workspace_manager.get_active_workspace("gamma")
    assert reloaded.vault_data.mappings == {}
    assert reloaded.vault_data.token_counter == {}
    assert reloaded.vault_data.file_records == []
