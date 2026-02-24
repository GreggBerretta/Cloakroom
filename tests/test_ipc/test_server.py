"""Tests for IPC server dispatch and error classification."""

from __future__ import annotations

from pathlib import Path

import pytest

from cloakroom import licensing
from cloakroom.ipc.protocol import PROTOCOL_VERSION
from cloakroom.ipc.server import IPCServer
from cloakroom.models import VaultData, now_iso
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class FakeManager:
    def __init__(self, ctx: WorkspaceContext):
        self._ctx = ctx

    def get_or_create_workspace(self, name: str, ttl_hours: int = 168) -> WorkspaceContext:
        return self._ctx

    def get_active_workspace(self, name: str) -> WorkspaceContext:
        return self._ctx

    def list_workspaces(self) -> list[dict]:
        return [
            {
                "name": self._ctx.workspace_name,
                "workspace_id": self._ctx.workspace_id,
                "status": "active",
                "mappings": len(self._ctx.vault_data.mappings),
                "files": len(self._ctx.vault_data.file_records),
            }
        ]

    def get_workspace_metadata(self, name: str) -> dict:
        return {"workspace_id": self._ctx.workspace_id}


class TestIPCServer:
    def test_hello_handshake(self, tmp_path):
        server = IPCServer(tmp_path / "engine.sock", manager=_fake_manager(tmp_path))
        response = server.handle_request_dict(
            _request(
                "HELLO",
                workspace_version="",
            )
        )

        assert response["status"] == "SUCCESS"
        assert response["payload"]["protocol_version"] == PROTOCOL_VERSION
        assert "schema_hash" in response["payload"]
        assert "supported_hebrew_backends" in response["payload"]
        assert response["payload"]["supported_ipc_modes"] == ["stdio", "unix_socket"]

    def test_unknown_type_is_hard_fail(self, tmp_path):
        server = IPCServer(tmp_path / "engine.sock", manager=_fake_manager(tmp_path))
        response = server.handle_request_dict(_request("UNKNOWN_TYPE"))

        assert response["status"] == "HARD_FAIL"
        assert response["error_code"] == "IPCError"

    def test_missing_required_envelope_field_is_hard_fail(self, tmp_path):
        server = IPCServer(tmp_path / "engine.sock", manager=_fake_manager(tmp_path))
        bad = _request("HEARTBEAT")
        bad.pop("request_id")
        response = server.handle_request_dict(bad)

        assert response["status"] == "HARD_FAIL"
        assert response["error_code"] == "IPCError"

    def test_stats_query_success(self, tmp_path):
        manager = _fake_manager(tmp_path)
        ctx = manager.get_active_workspace("default")
        server = IPCServer(tmp_path / "engine.sock", manager=manager)

        response = server.handle_request_dict(
            _request(
                "STATS_QUERY",
                workspace_version=ctx.vault_data.updated_at,
            )
        )

        assert response["status"] == "SUCCESS"
        assert response["payload"]["workspace_name"] == ctx.workspace_name
        assert "anonymize_count" in response["payload"]
        assert response["payload"]["license"]["tier"] == "FREE"

    def test_workspace_version_mismatch_is_validation_error(self, tmp_path):
        server = IPCServer(tmp_path / "engine.sock", manager=_fake_manager(tmp_path))
        response = server.handle_request_dict(
            _request(
                "STATS_QUERY",
                workspace_version="stale-version",
            )
        )

        assert response["status"] == "VALIDATION_ERROR"
        assert response["error_code"] == "WorkspaceSyncError"

    def test_inspect_columns_success(self, tmp_path):
        server = IPCServer(tmp_path / "engine.sock", manager=_fake_manager(tmp_path))
        response = server.handle_request_dict(
            _request(
                "INSPECT_COLUMNS",
                workspace_version="",
                payload={"file_path": str(FIXTURES_DIR / "sample_data.csv")},
            )
        )

        assert response["status"] == "SUCCESS"
        columns = response["payload"]["columns"]
        assert columns
        assert columns[0]["letter"] == "A"

    def test_invalid_license_key_returns_validation_error(self, tmp_path):
        manager = _fake_manager(tmp_path)
        ctx = manager.get_active_workspace("default")
        server = IPCServer(tmp_path / "engine.sock", manager=manager)
        response = server.handle_request_dict(
            _request(
                "STATS_QUERY",
                workspace_version=ctx.vault_data.updated_at,
                payload={"license_key": "bad-key"},
            )
        )

        assert response["status"] == "VALIDATION_ERROR"
        assert response["error_code"] == "LicenseKeyInvalidError"

    def test_column_selective_requires_pro_license(self, tmp_path):
        manager = _fake_manager(tmp_path)
        ctx = manager.get_active_workspace("default")
        server = IPCServer(tmp_path / "engine.sock", manager=manager)
        response = server.handle_request_dict(
            _request(
                "ANONYMIZE_FILE",
                workspace_version=ctx.vault_data.updated_at,
                payload={
                    "file_path": str(FIXTURES_DIR / "sample_data.csv"),
                    "columns": ["A"],
                    "license_key": "",
                },
            )
        )

        assert response["status"] == "VALIDATION_ERROR"
        assert response["error_code"] == "LicenseFeatureError"

    def test_free_restore_limit_enforced(self, tmp_path, monkeypatch: pytest.MonkeyPatch):
        usage_path = tmp_path / "license_usage.json"
        monkeypatch.setattr(licensing, "LICENSE_USAGE_PATH", usage_path)

        manager = _fake_manager(tmp_path)
        ctx = manager.get_active_workspace("default")
        server = IPCServer(tmp_path / "engine.sock", manager=manager)
        for idx in range(licensing.FREE_RESTORE_DAILY_LIMIT):
            response = server.handle_request_dict(
                _request(
                    "CLIPBOARD_RESTORE",
                    workspace_version=ctx.vault_data.updated_at,
                    payload={"license_key": ""},
                    request_id=f"req-{idx}",
                )
            )
            # Will fail business restore due to missing tokens, but license check passes first.
            assert response["status"] in {"VALIDATION_ERROR", "ERROR", "HARD_FAIL"}
            if response["error_code"] == "LicenseLimitExceededError":
                pytest.fail("limit should not be exceeded before quota is consumed")

        limited = server.handle_request_dict(
            _request(
                "CLIPBOARD_RESTORE",
                workspace_version=ctx.vault_data.updated_at,
                payload={"license_key": ""},
                request_id="req-over",
            )
        )
        assert limited["status"] == "VALIDATION_ERROR"
        assert limited["error_code"] == "LicenseLimitExceededError"


def _workspace_context(tmp_path: Path) -> WorkspaceContext:
    master_key = generate_master_key()
    hmac_key = derive_hmac_key(master_key)
    vault = Vault(tmp_path / "vault.enc")
    data = VaultData(
        workspace_id="ws-id",
        workspace_name="default",
        created_at=now_iso(),
        updated_at=now_iso(),
        ttl_hours=168,
    )
    token_generator = TokenGenerator(hmac_key)
    return WorkspaceContext(
        workspace_id="ws-id",
        workspace_name="default",
        vault=vault,
        vault_data=data,
        token_generator=token_generator,
        master_key=master_key,
    )


def _fake_manager(tmp_path: Path) -> FakeManager:
    return FakeManager(_workspace_context(tmp_path))


def _request(
    request_type: str,
    *,
    workspace_version: str = "",
    payload: dict | None = None,
    request_id: str = "req-1",
) -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "engine_version": "0.2.0",
        "request_id": request_id,
        "type": request_type,
        "workspace_id": "default",
        "workspace_version": workspace_version,
        "payload": payload or {},
    }
