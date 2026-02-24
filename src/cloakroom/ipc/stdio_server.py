"""Subprocess stdio IPC mode for wrapper compatibility."""

from __future__ import annotations

import argparse
import logging as py_logging
import sys
from pathlib import Path

from cloakroom.exceptions import IPCError
from cloakroom.ipc.framing import recv_frame_stream, send_frame_stream
from cloakroom.ipc.server import IPCServer
from cloakroom.logging import configure_logging, log_event


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cloakroom IPC stdio bridge")
    parser.add_argument(
        "--workspace-base-dir",
        default="",
        help="Optional workspace base directory override (for tests/debug only).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging (sanitized).")
    parser.add_argument("--no-logging", action="store_true", help="Disable non-audit logs.")
    parser.add_argument("--encrypt-logs", action="store_true", help="Encrypt local log files at rest.")
    return parser


def serve_stdio(server: IPCServer) -> None:
    # Keep this mode deterministic: one process can serve many framed requests
    # over stdin/stdout until EOF.
    while True:
        try:
            request = recv_frame_stream(sys.stdin.buffer)
        except IPCError:
            break
        except Exception:
            break

        response = server.handle_request_dict(request)
        try:
            send_frame_stream(sys.stdout.buffer, response)
        except Exception:
            break

        if request.get("type", "").upper() == "SHUTDOWN":
            break


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    configure_logging(
        component="engine",
        verbose=args.verbose,
        no_logging=args.no_logging,
        encrypt_logs=args.encrypt_logs,
    )
    log_event(
        "engine",
        py_logging.INFO,
        "ipc_stdio_start",
        "IPC stdio bridge started",
    )
    manager = None
    if args.workspace_base_dir:
        from cloakroom.workspace.manager import WorkspaceManager

        manager = WorkspaceManager(base_dir=Path(args.workspace_base_dir).expanduser())

    server = IPCServer(Path.home() / ".cloakroom" / "ipc" / "stdio.sock", manager=manager)
    try:
        serve_stdio(server)
    finally:
        log_event(
            "engine",
            py_logging.INFO,
            "ipc_stdio_stop",
            "IPC stdio bridge stopped",
        )


if __name__ == "__main__":
    main()
