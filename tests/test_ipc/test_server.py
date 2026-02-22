"""Tests for IPC server dispatch and error classification."""

from __future__ import annotations

from pathlib import Path

from cowork_shield.ipc.protocol import PROTOCOL_VERSION
from cowork_shield.ipc.server import IPCServer
from cowork_shield.models import VaultData, now_iso
from cowork_shield.tokenizer.generator import TokenGenerator
from cowork_shield.vault.crypto import derive_hmac_key, generate_master_key
from cowork_shield.vault.vault import Vault
from cowork_shield.workspace.manager import WorkspaceContext

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
) -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "engine_version": "0.2.0",
        "request_id": "req-1",
        "type": request_type,
        "workspace_id": "default",
        "workspace_version": workspace_version,
        "payload": payload or {},
    }
