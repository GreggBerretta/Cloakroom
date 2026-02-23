"""IPC server modules for Swift wrapper integration."""

from cowork_shield.ipc.protocol import PROTOCOL_VERSION, SCHEMA_HASH
from cowork_shield.ipc.server import IPCServer
from cowork_shield.ipc.stdio_server import main as stdio_main

__all__ = ["IPCServer", "PROTOCOL_VERSION", "SCHEMA_HASH", "stdio_main"]
