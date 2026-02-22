"""IPC server modules for Swift wrapper integration."""

from cowork_shield.ipc.protocol import PROTOCOL_VERSION, SCHEMA_HASH
from cowork_shield.ipc.server import IPCServer

__all__ = ["IPCServer", "PROTOCOL_VERSION", "SCHEMA_HASH"]
