"""IPC protocol contracts for the Swift wrapper bridge."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Any

from cowork_shield import __version__ as ENGINE_VERSION
from cowork_shield.exceptions import IPCError

PROTOCOL_VERSION = "2.0"

REQUEST_REQUIRED_FIELDS = (
    "protocol_version",
    "engine_version",
    "request_id",
    "type",
    "workspace_id",
    "workspace_version",
    "payload",
)

RESPONSE_REQUIRED_FIELDS = (
    "protocol_version",
    "engine_version",
    "request_id",
    "type",
    "workspace_id",
    "workspace_version",
    "status",
    "payload",
)

COMMON_PAYLOAD_OPTIONAL_FIELDS = (
    "columns",
    "detect_pii",
    "detection_mode",
    "hebrew_backend",
    "pdf_output_format",
    "force_reanonymize",
    "reason",
    "license_key",
)

_SCHEMA_DESCRIPTOR = {
    "protocol_version": PROTOCOL_VERSION,
    "request_fields": list(REQUEST_REQUIRED_FIELDS),
    "response_fields": list(RESPONSE_REQUIRED_FIELDS),
    "common_payload_optional_fields": list(COMMON_PAYLOAD_OPTIONAL_FIELDS),
    "statuses": ["SUCCESS", "VALIDATION_ERROR", "ERROR", "HARD_FAIL"],
}

SCHEMA_HASH = hashlib.sha256(
    json.dumps(_SCHEMA_DESCRIPTOR, sort_keys=True).encode("utf-8")
).hexdigest()


class IPCStatus(str, Enum):
    """IPC response statuses."""

    SUCCESS = "SUCCESS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    ERROR = "ERROR"
    HARD_FAIL = "HARD_FAIL"


@dataclass(frozen=True)
class IPCRequest:
    """Validated wrapper-to-engine IPC request."""

    protocol_version: str
    engine_version: str
    request_id: str
    type: str
    workspace_id: str
    workspace_version: str
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IPCRequest":
        _validate_required_fields(data, REQUEST_REQUIRED_FIELDS, envelope_type="request")

        protocol_version = _expect_str(data["protocol_version"], field="protocol_version")
        if protocol_version != PROTOCOL_VERSION:
            raise IPCError(
                "Protocol version mismatch: "
                f"expected {PROTOCOL_VERSION}, got {protocol_version}"
            )

        payload = data["payload"]
        if not isinstance(payload, dict):
            raise IPCError("Invalid request envelope: payload must be a JSON object")
        _validate_common_payload_fields(payload)

        return cls(
            protocol_version=protocol_version,
            engine_version=_expect_str(data["engine_version"], field="engine_version"),
            request_id=_expect_non_empty_str(data["request_id"], field="request_id"),
            type=_expect_non_empty_str(data["type"], field="type").upper(),
            workspace_id=_expect_non_empty_str(data["workspace_id"], field="workspace_id"),
            workspace_version=_expect_str(data["workspace_version"], field="workspace_version"),
            payload=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "engine_version": self.engine_version,
            "request_id": self.request_id,
            "type": self.type,
            "workspace_id": self.workspace_id,
            "workspace_version": self.workspace_version,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class IPCResponse:
    """Engine-to-wrapper IPC response."""

    protocol_version: str
    engine_version: str
    request_id: str
    type: str
    workspace_id: str
    workspace_version: str
    status: IPCStatus
    payload: dict[str, Any]
    error_code: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        body = {
            "protocol_version": self.protocol_version,
            "engine_version": self.engine_version,
            "request_id": self.request_id,
            "type": self.type,
            "workspace_id": self.workspace_id,
            "workspace_version": self.workspace_version,
            "status": self.status.value,
            "payload": self.payload,
        }
        if self.error_code:
            body["error_code"] = self.error_code
        if self.error_message:
            body["error_message"] = self.error_message
        return body

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IPCResponse":
        _validate_required_fields(data, RESPONSE_REQUIRED_FIELDS, envelope_type="response")
        payload = data["payload"]
        if not isinstance(payload, dict):
            raise IPCError("Invalid response envelope: payload must be a JSON object")

        return cls(
            protocol_version=_expect_str(data["protocol_version"], field="protocol_version"),
            engine_version=_expect_str(data["engine_version"], field="engine_version"),
            request_id=_expect_non_empty_str(data["request_id"], field="request_id"),
            type=_expect_non_empty_str(data["type"], field="type"),
            workspace_id=_expect_non_empty_str(data["workspace_id"], field="workspace_id"),
            workspace_version=_expect_str(data["workspace_version"], field="workspace_version"),
            status=IPCStatus(_expect_str(data["status"], field="status")),
            payload=payload,
            error_code=_expect_str(data.get("error_code", ""), field="error_code"),
            error_message=_expect_str(data.get("error_message", ""), field="error_message"),
        )


def build_success_response(
    request: IPCRequest,
    *,
    payload: dict[str, Any],
    workspace_version: str,
) -> IPCResponse:
    return IPCResponse(
        protocol_version=PROTOCOL_VERSION,
        engine_version=ENGINE_VERSION,
        request_id=request.request_id,
        type=request.type,
        workspace_id=request.workspace_id,
        workspace_version=workspace_version,
        status=IPCStatus.SUCCESS,
        payload=payload,
    )


def build_error_response(
    request: IPCRequest,
    *,
    status: IPCStatus,
    error_code: str,
    error_message: str,
    workspace_version: str,
    payload: dict[str, Any] | None = None,
) -> IPCResponse:
    return IPCResponse(
        protocol_version=PROTOCOL_VERSION,
        engine_version=ENGINE_VERSION,
        request_id=request.request_id,
        type=request.type,
        workspace_id=request.workspace_id,
        workspace_version=workspace_version,
        status=status,
        error_code=error_code,
        error_message=error_message,
        payload=payload or {},
    )


def build_hello_payload(
    *,
    model_hash: str,
    supported_hebrew_backends: tuple[str, ...],
    supported_detection_modes: tuple[str, ...],
    supported_pdf_output_formats: tuple[str, ...],
    supported_ipc_modes: tuple[str, ...],
) -> dict[str, Any]:
    """Payload returned for HELLO handshake."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "engine_version": ENGINE_VERSION,
        "schema_hash": SCHEMA_HASH,
        "model_hash": model_hash,
        "supported_hebrew_backends": list(supported_hebrew_backends),
        "supported_detection_modes": list(supported_detection_modes),
        "supported_pdf_output_formats": list(supported_pdf_output_formats),
        "supported_ipc_modes": list(supported_ipc_modes),
    }


def _validate_required_fields(
    data: dict[str, Any],
    required_fields: tuple[str, ...],
    *,
    envelope_type: str,
) -> None:
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise IPCError(
            f"Invalid {envelope_type} envelope: missing fields {', '.join(missing)}"
        )


def _expect_non_empty_str(value: Any, *, field: str) -> str:
    text = _expect_str(value, field=field)
    if not text:
        raise IPCError(f"Invalid envelope: '{field}' must be a non-empty string")
    return text


def _expect_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise IPCError(f"Invalid envelope: '{field}' must be a string")
    return value


def _validate_common_payload_fields(payload: dict[str, Any]) -> None:
    columns = payload.get("columns")
    if columns is not None and not isinstance(columns, (list, str)):
        raise IPCError("Invalid payload: 'columns' must be an array or comma-separated string")

    detect_pii = payload.get("detect_pii")
    if detect_pii is not None and not isinstance(detect_pii, bool):
        raise IPCError("Invalid payload: 'detect_pii' must be a boolean")

    force_reanonymize = payload.get("force_reanonymize")
    if force_reanonymize is not None and not isinstance(force_reanonymize, bool):
        raise IPCError("Invalid payload: 'force_reanonymize' must be a boolean")

    for key in ("detection_mode", "hebrew_backend", "pdf_output_format", "reason", "license_key"):
        value = payload.get(key)
        if value is not None and not isinstance(value, str):
            raise IPCError(f"Invalid payload: '{key}' must be a string")
