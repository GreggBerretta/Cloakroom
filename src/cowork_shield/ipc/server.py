"""UNIX-domain socket IPC server for the Swift wrapper."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
from typing import Any

from cowork_shield import __version__ as ENGINE_VERSION
from cowork_shield.clipboard.operations import restore_clipboard, shield_clipboard
from cowork_shield.detection.engine import DetectionEngine
from cowork_shield.detection.engine import HEBREW_BACKEND_CHOICES
from cowork_shield.exceptions import (
    CoWorkShieldError,
    ColumnSelectionError,
    DetectionError,
    HallucinationDetectedError,
    IncompleteRestorationError,
    IntegrityError,
    IPCError,
    KeychainError,
    ModelHashMismatchError,
    PdfInputOnlyError,
    ReplayMismatchError,
    RecoveryKeyError,
    LicenseFeatureError,
    LicenseKeyInvalidError,
    LicenseLimitExceededError,
    UnsupportedFormatError,
    VaultCorruptedError,
    WorkspaceExpiredError,
    WorkspaceNotFoundError,
    XLSXContentLossRiskError,
)
from cowork_shield.ipc.framing import recv_frame, send_frame
from cowork_shield.ipc.protocol import (
    IPCRequest,
    IPCStatus,
    PROTOCOL_VERSION,
    build_error_response,
    build_hello_payload,
    build_success_response,
)
from cowork_shield.licensing import enforce_license_policy, resolve_license_context
from cowork_shield.pipeline.anonymize import AnonymizePipeline
from cowork_shield.pipeline.columns import inspect_columns
from cowork_shield.pipeline.restore import RestorePipeline
from cowork_shield.vault.keychain import get_master_key, store_master_key
from cowork_shield.vault.recovery import (
    export_encrypted_master_key,
    import_encrypted_master_key,
)
from cowork_shield.workspace.manager import WorkspaceContext, WorkspaceManager


class WorkspaceSyncError(CoWorkShieldError):
    """Wrapper workspace identity/version does not match engine state."""


@dataclass(frozen=True)
class DispatchResult:
    payload: dict[str, Any]
    workspace_version: str


class IPCServer:
    """Length-prefixed JSON IPC server over AF_UNIX."""

    EXPECTED_VALIDATION_ERRORS = (
        ColumnSelectionError,
        PdfInputOnlyError,
        UnsupportedFormatError,
        WorkspaceExpiredError,
        WorkspaceNotFoundError,
        RecoveryKeyError,
        ReplayMismatchError,
        ModelHashMismatchError,
        HallucinationDetectedError,
        IncompleteRestorationError,
        XLSXContentLossRiskError,
        WorkspaceSyncError,
        LicenseFeatureError,
        LicenseKeyInvalidError,
        LicenseLimitExceededError,
    )

    HARD_FAIL_ERRORS = (
        IPCError,
        VaultCorruptedError,
        KeychainError,
        IntegrityError,
        DetectionError,
    )

    def __init__(self, socket_path: Path | str, *, manager: WorkspaceManager | None = None):
        self._socket_path = Path(socket_path).expanduser().resolve()
        self._manager = manager or WorkspaceManager()
        self._server_sock: socket.socket | None = None
        self._running = False

    def serve_forever(self) -> None:
        self._prepare_socket()
        self._running = True

        assert self._server_sock is not None
        while self._running:
            conn, _ = self._server_sock.accept()
            with conn:
                self._serve_client(conn)

    def stop(self) -> None:
        self._running = False
        if self._server_sock is not None:
            self._server_sock.close()
            self._server_sock = None
        self._cleanup_socket_file()

    def _prepare_socket(self) -> None:
        self._cleanup_socket_file()
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(str(self._socket_path))
        os.chmod(self._socket_path, 0o600)
        server_sock.listen(8)
        self._server_sock = server_sock

    def _cleanup_socket_file(self) -> None:
        try:
            if self._socket_path.exists():
                self._socket_path.unlink()
        except OSError:
            pass

    def _serve_client(self, conn: socket.socket) -> None:
        while self._running:
            try:
                raw = recv_frame(conn)
            except IPCError:
                # Protocol framing failed before we can build a safe response envelope.
                return
            except Exception:
                return

            response = self.handle_request_dict(raw)
            try:
                send_frame(conn, response)
            except Exception:
                return

            if raw.get("type", "").upper() == "SHUTDOWN":
                self._running = False
                return

    def handle_request_dict(self, raw: dict[str, Any]) -> dict[str, Any]:
        request: IPCRequest | None = None
        try:
            request = IPCRequest.from_dict(raw)
            result = self._dispatch(request)
            response = build_success_response(
                request,
                payload=result.payload,
                workspace_version=result.workspace_version,
            )
            return response.to_dict()

        except self.EXPECTED_VALIDATION_ERRORS as exc:
            if request is None:
                return self._hard_fail_envelope(raw, error=exc)
            response = build_error_response(
                request,
                status=IPCStatus.VALIDATION_ERROR,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
                workspace_version=self._response_workspace_version(request),
            )
            return response.to_dict()

        except self.HARD_FAIL_ERRORS as exc:
            if request is None:
                return self._hard_fail_envelope(raw, error=exc)
            response = build_error_response(
                request,
                status=IPCStatus.HARD_FAIL,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
                workspace_version=self._response_workspace_version(request),
            )
            return response.to_dict()

        except Exception as exc:  # noqa: BLE001
            if request is None:
                return self._hard_fail_envelope(raw, error=exc)
            response = build_error_response(
                request,
                status=IPCStatus.ERROR,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
                workspace_version=self._response_workspace_version(request),
            )
            return response.to_dict()

    def _dispatch(self, request: IPCRequest) -> DispatchResult:
        request_type = request.type
        if request_type == "HELLO":
            return self._dispatch_hello(request)
        if request_type == "SHUTDOWN":
            return DispatchResult(payload={"accepted": True}, workspace_version=request.workspace_version)

        license_context = resolve_license_context(request.payload)
        license_usage = enforce_license_policy(
            request_type=request_type,
            payload=request.payload,
            license_context=license_context,
        )

        dispatch_result: DispatchResult
        if request_type == "HEARTBEAT":
            dispatch_result = self._dispatch_heartbeat(request)
        elif request_type == "WORKSPACE_SWITCH":
            dispatch_result = self._dispatch_workspace_switch(request)
        elif request_type == "ANONYMIZE_FILE":
            dispatch_result = self._dispatch_anonymize_file(request)
        elif request_type == "RESTORE_FILE":
            dispatch_result = self._dispatch_restore_file(request)
        elif request_type == "CLIPBOARD_ANONYMIZE":
            dispatch_result = self._dispatch_clipboard_anonymize(request)
        elif request_type == "CLIPBOARD_RESTORE":
            dispatch_result = self._dispatch_clipboard_restore(request)
        elif request_type == "VAULT_EXPORT_KEY":
            dispatch_result = self._dispatch_vault_export_key(request)
        elif request_type == "VAULT_IMPORT_KEY":
            dispatch_result = self._dispatch_vault_import_key(request)
        elif request_type == "STATS_QUERY":
            dispatch_result = self._dispatch_stats_query(request)
        elif request_type == "INSPECT_COLUMNS":
            dispatch_result = self._dispatch_inspect_columns(request)
        else:
            raise IPCError(f"Unsupported IPC request type: {request.type}")

        payload = dict(dispatch_result.payload)
        payload["license"] = {
            "tier": license_context.tier,
            "key_present": license_context.key_present,
            "key_fingerprint": license_context.key_fingerprint,
            **license_usage,
        }
        return DispatchResult(
            payload=payload,
            workspace_version=dispatch_result.workspace_version,
        )

    def _dispatch_hello(self, request: IPCRequest) -> DispatchResult:
        detection = DetectionEngine(score_threshold=0.7)
        payload = build_hello_payload(
            model_hash=detection.get_model_hash(),
            supported_hebrew_backends=HEBREW_BACKEND_CHOICES,
            supported_pdf_output_formats=("md", "docx"),
            supported_ipc_modes=("stdio", "unix_socket"),
        )
        return DispatchResult(payload=payload, workspace_version=request.workspace_version)

    def _dispatch_heartbeat(self, request: IPCRequest) -> DispatchResult:
        return DispatchResult(
            payload={
                "alive": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "protocol_version": PROTOCOL_VERSION,
            },
            workspace_version=request.workspace_version,
        )

    def _dispatch_workspace_switch(self, request: IPCRequest) -> DispatchResult:
        ttl_hours = int(request.payload.get("ttl_hours", 168))
        create_if_missing = bool(request.payload.get("create_if_missing", True))

        workspace_name = self._resolve_workspace_name(
            request.workspace_id,
            allow_missing=create_if_missing,
        )

        if create_if_missing:
            ctx = self._manager.get_or_create_workspace(workspace_name, ttl_hours=ttl_hours)
        else:
            ctx = self._manager.get_active_workspace(workspace_name)

        payload = {
            "workspace_id": ctx.workspace_id,
            "workspace_name": ctx.workspace_name,
            "workspace_version": ctx.vault_data.updated_at,
        }
        return DispatchResult(payload=payload, workspace_version=ctx.vault_data.updated_at)

    def _dispatch_anonymize_file(self, request: IPCRequest) -> DispatchResult:
        ctx = self._load_workspace(request, create_if_missing=True)
        payload = request.payload
        file_path = self._require_str(payload, "file_path")

        output_raw = payload.get("output_path", "")
        output_path = Path(output_raw).expanduser() if isinstance(output_raw, str) and output_raw else None

        columns = payload.get("columns", [])
        if isinstance(columns, str):
            selected_columns = [part.strip() for part in columns.split(",") if part.strip()]
        elif isinstance(columns, list):
            selected_columns = [str(part).strip() for part in columns if str(part).strip()]
        else:
            raise ColumnSelectionError("'columns' must be an array of strings or comma-separated string")

        force_reanonymize = bool(payload.get("force_reanonymize", False))
        override_reason = str(payload.get("reason", "")).strip()
        if force_reanonymize and not override_reason:
            raise CoWorkShieldError("force_reanonymize requires a non-empty reason")

        pipeline = AnonymizePipeline(
            ctx,
            score_threshold=float(payload.get("score_threshold", 0.7)),
            language=str(payload.get("language", "auto")),
            hebrew_backend=str(payload.get("hebrew_backend", "auto")),
            hebrew_stanza_model=str(payload.get("hebrew_stanza_model", "he")),
            hebrew_transformer_model=str(
                payload.get("hebrew_transformer_model", "CordwainerSmith/GolemPII-v1")
            ),
            allow_lossy_xlsx=bool(payload.get("allow_lossy_xlsx", False)),
            pdf_output_format=str(payload.get("pdf_output_format", "md")),
            selected_columns=selected_columns,
            detect_pii=payload.get("detect_pii", None),
            force_reanonymize=force_reanonymize,
            override_reason=override_reason,
            override_user="swift-wrapper",
        )
        result = pipeline.run(Path(file_path).expanduser(), output_path)
        return DispatchResult(
            payload={
                "input_path": str(result.input_path),
                "output_path": str(result.output_path),
                "backup_path": str(result.backup_path) if result.backup_path else "",
                "workspace_name": result.workspace_name,
                "entities_found": result.entities_found,
                "tokens_applied": result.tokens_applied,
            },
            workspace_version=ctx.vault_data.updated_at,
        )

    def _dispatch_restore_file(self, request: IPCRequest) -> DispatchResult:
        ctx = self._load_workspace(request, create_if_missing=False)
        payload = request.payload
        file_path = self._require_str(payload, "file_path")

        output_raw = payload.get("output_path", "")
        output_path = Path(output_raw).expanduser() if isinstance(output_raw, str) and output_raw else None

        result = RestorePipeline(ctx).run(Path(file_path).expanduser(), output_path)
        return DispatchResult(
            payload={
                "input_path": str(result.input_path),
                "output_path": str(result.output_path),
                "workspace_name": result.workspace_name,
                "tokens_restored": result.tokens_restored,
                "verification_passed": result.verification_passed,
            },
            workspace_version=ctx.vault_data.updated_at,
        )

    def _dispatch_clipboard_anonymize(self, request: IPCRequest) -> DispatchResult:
        ctx = self._load_workspace(request, create_if_missing=True)
        payload = request.payload

        force_reanonymize = bool(payload.get("force_reanonymize", False))
        override_reason = str(payload.get("reason", "")).strip()
        if force_reanonymize and not override_reason:
            raise CoWorkShieldError("force_reanonymize requires a non-empty reason")

        result = shield_clipboard(
            ctx,
            score_threshold=float(payload.get("score_threshold", 0.7)),
            language=str(payload.get("language", "auto")),
            hebrew_backend=str(payload.get("hebrew_backend", "auto")),
            hebrew_stanza_model=str(payload.get("hebrew_stanza_model", "he")),
            hebrew_transformer_model=str(
                payload.get("hebrew_transformer_model", "CordwainerSmith/GolemPII-v1")
            ),
            force_reanonymize=force_reanonymize,
            override_reason=override_reason,
            override_user="swift-wrapper",
        )

        return DispatchResult(
            payload={
                "entities_found": result.entities_found,
                "tokens_applied": result.tokens_applied,
                "model_hash": result.model_hash,
            },
            workspace_version=ctx.vault_data.updated_at,
        )

    def _dispatch_clipboard_restore(self, request: IPCRequest) -> DispatchResult:
        ctx = self._load_workspace(request, create_if_missing=False)
        result = restore_clipboard(ctx)
        return DispatchResult(
            payload={
                "tokens_restored": result.tokens_restored,
                "verification_passed": result.verification_passed,
            },
            workspace_version=ctx.vault_data.updated_at,
        )

    def _dispatch_vault_export_key(self, request: IPCRequest) -> DispatchResult:
        ctx = self._load_workspace(request, create_if_missing=False)
        output_path = Path(self._require_str(request.payload, "output_path")).expanduser()
        passphrase = self._require_str(request.payload, "passphrase")

        blob = export_encrypted_master_key(
            workspace_id=ctx.workspace_id,
            master_key=ctx.master_key,
            passphrase=passphrase,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(blob)
        os.chmod(output_path, 0o600)

        return DispatchResult(
            payload={
                "workspace_id": ctx.workspace_id,
                "output_path": str(output_path),
            },
            workspace_version=ctx.vault_data.updated_at,
        )

    def _dispatch_vault_import_key(self, request: IPCRequest) -> DispatchResult:
        input_path = Path(self._require_str(request.payload, "input_path")).expanduser()
        passphrase = self._require_str(request.payload, "passphrase")
        force = bool(request.payload.get("force", False))

        workspace_name = self._resolve_workspace_name(request.workspace_id, allow_missing=False)
        metadata = self._manager.get_workspace_metadata(workspace_name)
        expected_workspace_id = str(metadata["workspace_id"])

        blob = input_path.read_bytes()
        workspace_id, master_key = import_encrypted_master_key(
            blob=blob,
            passphrase=passphrase,
            expected_workspace_id=expected_workspace_id,
        )

        existing = get_master_key(workspace_id)
        if existing is not None and not force:
            raise CoWorkShieldError(
                "Keychain entry already exists for this workspace. "
                "Set force=true to overwrite."
            )

        store_master_key(workspace_id, master_key)

        ctx = self._manager.get_active_workspace(workspace_name)
        return DispatchResult(
            payload={
                "workspace_id": workspace_id,
                "workspace_name": workspace_name,
                "imported": True,
            },
            workspace_version=ctx.vault_data.updated_at,
        )

    def _dispatch_stats_query(self, request: IPCRequest) -> DispatchResult:
        ctx = self._load_workspace(request, create_if_missing=False)
        data = ctx.vault_data
        payload = {
            "workspace_id": ctx.workspace_id,
            "workspace_name": ctx.workspace_name,
            "workspace_version": data.updated_at,
            "anonymize_count": data.anonymize_count,
            "restore_count": data.restore_count,
            "abort_count": data.abort_count,
            "last_used": data.last_used,
            "mappings": len(data.mappings),
            "file_records": len(data.file_records),
            "token_abi_version": data.token_abi_version,
        }
        return DispatchResult(payload=payload, workspace_version=data.updated_at)

    def _dispatch_inspect_columns(self, request: IPCRequest) -> DispatchResult:
        path = Path(self._require_str(request.payload, "file_path")).expanduser()
        columns = inspect_columns(path)
        payload = {
            "columns": [
                {
                    "index": column.index,
                    "letter": column.letter,
                    "name": column.name,
                    "data_type": column.data_type,
                    "sample_values": list(column.sample_values),
                }
                for column in columns
            ],
        }
        # Inspect columns can run without an active workspace.
        return DispatchResult(payload=payload, workspace_version=request.workspace_version)

    def _load_workspace(self, request: IPCRequest, *, create_if_missing: bool) -> WorkspaceContext:
        workspace_name = self._resolve_workspace_name(
            request.workspace_id,
            allow_missing=create_if_missing,
        )

        if create_if_missing:
            ttl_hours = int(request.payload.get("ttl_hours", 168))
            ctx = self._manager.get_or_create_workspace(workspace_name, ttl_hours=ttl_hours)
        else:
            ctx = self._manager.get_active_workspace(workspace_name)

        if request.workspace_version and request.workspace_version != ctx.vault_data.updated_at:
            raise WorkspaceSyncError(
                "Workspace version mismatch: wrapper has "
                f"{request.workspace_version}, engine has {ctx.vault_data.updated_at}."
            )

        return ctx

    def _resolve_workspace_name(self, identifier: str, *, allow_missing: bool) -> str:
        for workspace in self._manager.list_workspaces():
            if workspace["name"] == identifier:
                return workspace["name"]
            if workspace["workspace_id"] == identifier:
                return workspace["name"]

        if allow_missing:
            return identifier

        raise WorkspaceNotFoundError(identifier)

    @staticmethod
    def _require_str(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise CoWorkShieldError(f"'{key}' must be a non-empty string")
        return value.strip()

    def _response_workspace_version(self, request: IPCRequest) -> str:
        identifier = request.workspace_id
        for workspace in self._manager.list_workspaces():
            if workspace["name"] == identifier or workspace["workspace_id"] == identifier:
                try:
                    ctx = self._manager.get_active_workspace(workspace["name"])
                    return ctx.vault_data.updated_at
                except Exception:  # noqa: BLE001
                    return request.workspace_version
        return request.workspace_version

    @staticmethod
    def _hard_fail_envelope(raw: dict[str, Any], *, error: Exception) -> dict[str, Any]:
        request_id = raw.get("request_id", "") if isinstance(raw, dict) else ""
        request_type = raw.get("type", "UNKNOWN") if isinstance(raw, dict) else "UNKNOWN"
        workspace_id = raw.get("workspace_id", "") if isinstance(raw, dict) else ""
        workspace_version = raw.get("workspace_version", "") if isinstance(raw, dict) else ""

        return {
            "protocol_version": PROTOCOL_VERSION,
            "engine_version": ENGINE_VERSION,
            "request_id": request_id if isinstance(request_id, str) else "",
            "type": request_type if isinstance(request_type, str) else "UNKNOWN",
            "workspace_id": workspace_id if isinstance(workspace_id, str) else "",
            "workspace_version": workspace_version if isinstance(workspace_version, str) else "",
            "status": IPCStatus.HARD_FAIL.value,
            "error_code": error.__class__.__name__,
            "error_message": str(error),
            "payload": {},
        }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CoWork Shield IPC socket server")
    parser.add_argument(
        "--socket-path",
        default=str(Path.home() / ".cowork-shield" / "ipc" / "engine.sock"),
        help="UNIX domain socket path",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    server = IPCServer(args.socket_path)
    try:
        server.serve_forever()
    finally:
        server.stop()


if __name__ == "__main__":
    main()
