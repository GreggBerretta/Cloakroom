"""Tests for subprocess stdio IPC mode."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import types

from cowork_shield.ipc.framing import encode_frame, recv_frame_stream
from cowork_shield.ipc.protocol import PROTOCOL_VERSION
from cowork_shield.ipc.server import IPCServer
from cowork_shield.ipc.stdio_server import serve_stdio
from cowork_shield.models import VaultData, now_iso
from cowork_shield.tokenizer.generator import TokenGenerator
from cowork_shield.vault.crypto import derive_hmac_key, generate_master_key
from cowork_shield.vault.vault import Vault
from cowork_shield.workspace.manager import WorkspaceContext


class _FakeManager:
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


def test_stdio_mode_round_trip(tmp_path, monkeypatch):
    ctx = _workspace_context(tmp_path)
    server = IPCServer(tmp_path / "stdio.sock", manager=_FakeManager(ctx))

    request = {
        "protocol_version": PROTOCOL_VERSION,
        "engine_version": "0.2.0",
        "request_id": "req-1",
        "type": "HEARTBEAT",
        "workspace_id": "default",
        "workspace_version": ctx.vault_data.updated_at,
        "payload": {"license_key": ""},
    }
    shutdown = {
        **request,
        "request_id": "req-2",
        "type": "SHUTDOWN",
    }
    stream_in = BytesIO(encode_frame(request) + encode_frame(shutdown))
    stream_out = BytesIO()

    fake_stdin = types.SimpleNamespace(buffer=stream_in)
    fake_stdout = types.SimpleNamespace(buffer=stream_out)

    monkeypatch.setattr("cowork_shield.ipc.stdio_server.sys.stdin", fake_stdin)
    monkeypatch.setattr("cowork_shield.ipc.stdio_server.sys.stdout", fake_stdout)

    serve_stdio(server)

    stream_out.seek(0)
    first = recv_frame_stream(stream_out)
    second = recv_frame_stream(stream_out)
    assert first["status"] == "SUCCESS"
    assert first["payload"]["alive"] is True
    assert second["status"] == "SUCCESS"
    assert second["payload"]["accepted"] is True


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

