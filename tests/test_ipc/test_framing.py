"""Tests for length-prefixed socket framing."""

from __future__ import annotations

import socket

import pytest

from cowork_shield.exceptions import IPCError
from cowork_shield.ipc.framing import recv_frame, send_frame


class TestIPCFraming:
    def test_send_and_receive_round_trip(self):
        left, right = socket.socketpair()
        try:
            payload = {"a": 1, "b": "hello"}
            send_frame(left, payload)
            decoded = recv_frame(right)
            assert decoded == payload
        finally:
            left.close()
            right.close()

    def test_partial_payload_fails_closed(self):
        left, right = socket.socketpair()
        try:
            body = b'{"x":1}'
            header = (len(body) + 5).to_bytes(8, "big")
            left.sendall(header + body)
            left.shutdown(socket.SHUT_WR)
            with pytest.raises(IPCError):
                recv_frame(right)
        finally:
            left.close()
            right.close()

    def test_non_json_payload_fails(self):
        left, right = socket.socketpair()
        try:
            body = b"not-json"
            header = len(body).to_bytes(8, "big")
            left.sendall(header + body)
            with pytest.raises(IPCError):
                recv_frame(right)
        finally:
            left.close()
            right.close()
