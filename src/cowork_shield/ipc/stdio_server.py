"""Subprocess stdio IPC mode for wrapper compatibility."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cowork_shield.exceptions import IPCError
from cowork_shield.ipc.framing import recv_frame_stream, send_frame_stream
from cowork_shield.ipc.server import IPCServer


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CoWork Shield IPC stdio bridge")
    parser.add_argument(
        "--workspace-base-dir",
        default="",
        help="Optional workspace base directory override (for tests/debug only).",
    )
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
    manager = None
    if args.workspace_base_dir:
        from cowork_shield.workspace.manager import WorkspaceManager

        manager = WorkspaceManager(base_dir=Path(args.workspace_base_dir).expanduser())

    server = IPCServer(Path.home() / ".cowork-shield" / "ipc" / "stdio.sock", manager=manager)
    serve_stdio(server)


if __name__ == "__main__":
    main()
