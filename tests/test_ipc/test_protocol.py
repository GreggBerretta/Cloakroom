"""Tests for IPC envelope validation."""

from __future__ import annotations

import pytest

from cowork_shield.exceptions import IPCError
from cowork_shield.ipc.protocol import (
    IPCRequest,
    IPCResponse,
    IPCStatus,
    PROTOCOL_VERSION,
)


def _base_request() -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "engine_version": "0.2.0",
        "request_id": "req-1",
        "type": "HELLO",
        "workspace_id": "default",
        "workspace_version": "",
        "payload": {},
    }


class TestIPCRequestValidation:
    def test_valid_request(self):
        req = IPCRequest.from_dict(_base_request())
        assert req.type == "HELLO"
        assert req.request_id == "req-1"

    def test_missing_required_field_fails(self):
        payload = _base_request()
        payload.pop("request_id")
        with pytest.raises(IPCError):
            IPCRequest.from_dict(payload)

    def test_protocol_version_mismatch_fails(self):
        payload = _base_request()
        payload["protocol_version"] = "9.9"
        with pytest.raises(IPCError):
            IPCRequest.from_dict(payload)

    def test_payload_must_be_object(self):
        payload = _base_request()
        payload["payload"] = []
        with pytest.raises(IPCError):
            IPCRequest.from_dict(payload)


class TestIPCResponseValidation:
    def test_valid_response(self):
        response = IPCResponse.from_dict(
            {
                "protocol_version": PROTOCOL_VERSION,
                "engine_version": "0.2.0",
                "request_id": "req-1",
                "type": "HELLO",
                "workspace_id": "default",
                "workspace_version": "",
                "status": "SUCCESS",
                "payload": {"ok": True},
            }
        )
        assert response.status == IPCStatus.SUCCESS

    def test_response_missing_field_fails(self):
        response = {
            "protocol_version": PROTOCOL_VERSION,
            "engine_version": "0.2.0",
            "request_id": "req-1",
            "type": "HELLO",
            "workspace_id": "default",
            "workspace_version": "",
            "status": "SUCCESS",
            # payload missing
        }
        with pytest.raises(IPCError):
            IPCResponse.from_dict(response)
