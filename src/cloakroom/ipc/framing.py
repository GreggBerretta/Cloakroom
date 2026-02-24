"""Length-prefixed IPC framing for UNIX-domain socket transport."""

from __future__ import annotations

import json
import socket
from typing import Any, BinaryIO

from cloakroom.exceptions import IPCError

HEADER_BYTES = 8
MAX_FRAME_BYTES = 16 * 1024 * 1024  # 16 MiB safety cap.


def encode_frame(payload: dict[str, Any]) -> bytes:
    """Serialize payload as `[8-byte length][JSON bytes]`."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_FRAME_BYTES:
        raise IPCError(f"IPC payload exceeds max frame size ({MAX_FRAME_BYTES} bytes)")
    return len(body).to_bytes(HEADER_BYTES, "big") + body


def send_frame(conn: socket.socket, payload: dict[str, Any]) -> None:
    """Write a framed payload to an active socket connection."""
    frame = encode_frame(payload)
    _send_all(conn, frame)


def recv_frame(conn: socket.socket) -> dict[str, Any]:
    """Read and decode one full framed JSON payload from socket."""
    header = _recv_exact(conn, HEADER_BYTES)
    if len(header) < HEADER_BYTES:
        raise IPCError("Partial IPC header received")

    body_len = int.from_bytes(header, "big")
    if body_len <= 0:
        raise IPCError("Invalid IPC frame length (must be > 0)")
    if body_len > MAX_FRAME_BYTES:
        raise IPCError(f"IPC frame length {body_len} exceeds max {MAX_FRAME_BYTES}")

    body = _recv_exact(conn, body_len)
    if len(body) < body_len:
        raise IPCError("Partial IPC payload received")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise IPCError(f"Malformed IPC JSON payload: {exc}") from exc

    if not isinstance(payload, dict):
        raise IPCError("IPC payload must decode to a JSON object")

    return payload


def send_frame_stream(stream: BinaryIO, payload: dict[str, Any]) -> None:
    """Write a framed payload to a binary stream (stdin/stdout mode)."""
    frame = encode_frame(payload)
    stream.write(frame)
    stream.flush()


def recv_frame_stream(stream: BinaryIO) -> dict[str, Any]:
    """Read and decode one framed JSON payload from a binary stream."""
    header = _read_exact(stream, HEADER_BYTES)
    if len(header) < HEADER_BYTES:
        raise IPCError("Partial IPC header received")

    body_len = int.from_bytes(header, "big")
    if body_len <= 0:
        raise IPCError("Invalid IPC frame length (must be > 0)")
    if body_len > MAX_FRAME_BYTES:
        raise IPCError(f"IPC frame length {body_len} exceeds max {MAX_FRAME_BYTES}")

    body = _read_exact(stream, body_len)
    if len(body) < body_len:
        raise IPCError("Partial IPC payload received")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise IPCError(f"Malformed IPC JSON payload: {exc}") from exc

    if not isinstance(payload, dict):
        raise IPCError("IPC payload must decode to a JSON object")

    return payload


def _send_all(conn: socket.socket, data: bytes) -> None:
    sent = 0
    while sent < len(data):
        written = conn.send(data[sent:])
        if written <= 0:
            raise IPCError("Socket send failed (peer closed)")
        sent += written


def _recv_exact(conn: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total < length:
        chunk = conn.recv(length - total)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total < length:
        chunk = stream.read(length - total)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)
