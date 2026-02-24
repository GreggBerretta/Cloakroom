"""Structured logging configuration for Cloakroom."""

from __future__ import annotations

import builtins
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import uuid
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cloakroom.logging.sanitizer import sanitize_exception, sanitize_text, sanitize_value

LOG_DIR = Path.home() / ".cloakroom" / "logs"
LOG_FILE = LOG_DIR / "cloakroom.log"
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
LOG_RETENTION_DAYS = 30
LOG_KEY_FILE = LOG_DIR / ".logkey"

COMPONENT_DEFAULT_LEVEL = {
    "cli": logging.WARNING,
    "tui": logging.WARNING,
    "gradio": logging.WARNING,
    "engine": logging.INFO,
}


@dataclass
class LoggingRuntimeConfig:
    component: str
    level: int
    verbose: bool
    no_logging: bool
    encrypt_logs: bool
    session_id: str


_runtime = LoggingRuntimeConfig(
    component="cli",
    level=logging.WARNING,
    verbose=False,
    no_logging=False,
    encrypt_logs=False,
    session_id=uuid.uuid4().hex,
)


class JsonLogFormatter(logging.Formatter):
    """JSON formatter with built-in sanitization."""

    def format(self, record: logging.LogRecord) -> str:
        message, message_sanitized = sanitize_text(record.getMessage())
        metadata_raw = getattr(record, "metadata", {})
        metadata, metadata_sanitized = sanitize_value(metadata_raw)
        error = getattr(record, "error", None)
        sanitized = bool(message_sanitized or metadata_sanitized)

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", _runtime.component),
            "event": getattr(record, "event", "log"),
            "message": message,
            "workspace_id": getattr(record, "workspace_id", ""),
            "session_id": getattr(record, "session_id", _runtime.session_id),
            "metadata": metadata or {},
            "sanitized": sanitized,
        }
        if error:
            payload["error"] = error
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)


class HumanLogFormatter(logging.Formatter):
    """Readable CLI formatter (mainly for debug stream handlers)."""

    def format(self, record: logging.LogRecord) -> str:
        message, _ = sanitize_text(record.getMessage())
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        component = getattr(record, "component", _runtime.component)
        event = getattr(record, "event", "log")
        return f"{timestamp} [{record.levelname}] [{component}] {event}: {message}"


class SecureRotatingFileHandler(RotatingFileHandler):
    """Rotating file handler that always creates files with 0600 permissions."""

    def _open(self):
        return builtins.open(
            self.baseFilename,
            self.mode,
            encoding=self.encoding,
            errors=self.errors,
            opener=_secure_opener,
        )


class EncryptedJsonFormatter(logging.Formatter):
    """Encrypt formatted JSON log lines for optional high-security mode."""

    def __init__(self, base_formatter: logging.Formatter):
        super().__init__()
        self._base = base_formatter
        self._key = _load_or_create_log_key()
        self._aesgcm = AESGCM(self._key)

    def format(self, record: logging.LogRecord) -> str:
        plaintext = self._base.format(record).encode("utf-8")
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, None)
        blob = (nonce + ciphertext).hex()
        return json.dumps({"encrypted": True, "blob": blob})


def configure_logging(
    *,
    component: str,
    verbose: bool = False,
    no_logging: bool = False,
    encrypt_logs: bool = False,
) -> LoggingRuntimeConfig:
    """Configure package logging once per process."""
    level = logging.DEBUG if verbose else COMPONENT_DEFAULT_LEVEL.get(component, logging.INFO)

    _runtime.component = component
    _runtime.level = level
    _runtime.verbose = verbose
    _runtime.no_logging = no_logging
    _runtime.encrypt_logs = encrypt_logs
    _runtime.session_id = uuid.uuid4().hex

    logger = logging.getLogger("cloakroom")
    logger.setLevel(level)
    logger.propagate = False
    logger.handlers.clear()

    if no_logging:
        logger.addHandler(logging.NullHandler())
        return _runtime

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _apply_log_retention()

    file_handler = SecureRotatingFileHandler(
        str(LOG_FILE),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    formatter: logging.Formatter = JsonLogFormatter()
    if encrypt_logs:
        formatter = EncryptedJsonFormatter(formatter)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    if verbose:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(HumanLogFormatter())
        stream_handler.setLevel(logging.DEBUG)
        logger.addHandler(stream_handler)

    return _runtime


def get_runtime_config() -> LoggingRuntimeConfig:
    return _runtime


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(f"cloakroom.{component}")


def log_event(
    component: str,
    level: int,
    event: str,
    message: str,
    *,
    workspace_id: str = "",
    metadata: dict[str, Any] | None = None,
    exc: Exception | None = None,
) -> None:
    """Log a sanitized structured event."""
    if _runtime.no_logging:
        return

    logger = get_logger(component)
    safe_message, msg_changed = sanitize_text(message)
    safe_metadata, meta_changed = sanitize_value(metadata or {})

    extra: dict[str, Any] = {
        "component": component,
        "event": event,
        "workspace_id": workspace_id,
        "session_id": _runtime.session_id,
        "metadata": safe_metadata,
    }
    if exc is not None:
        extra["error"] = sanitize_exception(exc, debug=_runtime.verbose)
    logger.log(level, safe_message, extra=extra)

    if (msg_changed or meta_changed) and event != "log_sanitization_triggered":
        logger.warning(
            "Log sanitization triggered",
            extra={
                "component": component,
                "event": "log_sanitization_triggered",
                "workspace_id": workspace_id,
                "session_id": _runtime.session_id,
                "metadata": {"source_event": event},
            },
        )


def list_log_files() -> list[Path]:
    if not LOG_DIR.exists():
        return []
    return sorted(
        path
        for path in LOG_DIR.glob("cloakroom.log*")
        if path.is_file()
    )


def export_log_files(output_path: Path) -> Path:
    """Export current application logs as sanitized JSON."""
    payload = collect_log_payload()
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.chmod(output_path, 0o600)
    return output_path


def collect_log_payload() -> dict[str, Any]:
    """Collect sanitized log entries from rotating files."""
    payload: dict[str, Any] = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session_id": _runtime.session_id,
        "files": [],
    }
    for path in list_log_files():
        entries: list[Any] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                raw = json.loads(line)
            except Exception:
                sanitized_line, _ = sanitize_text(line)
                entries.append({"raw": sanitized_line})
                continue
            sanitized, _ = sanitize_value(raw)
            entries.append(sanitized)
        payload["files"].append({"path": str(path), "entries": entries})
    return payload


def delete_log_files() -> int:
    """Delete all application log files under ~/.cloakroom/logs."""
    count = 0
    for path in list_log_files():
        try:
            path.unlink()
            count += 1
        except OSError:
            continue
    return count


def _apply_log_retention() -> None:
    cutoff = datetime.now(timezone.utc).timestamp() - (LOG_RETENTION_DAYS * 86400)
    for path in LOG_DIR.glob("cloakroom.log*"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def _secure_opener(path: str, flags: int) -> int:
    return os.open(path, flags, 0o600)


def _load_or_create_log_key() -> bytes:
    if LOG_KEY_FILE.exists():
        data = LOG_KEY_FILE.read_bytes()
        if len(data) == 32:
            return data
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    LOG_KEY_FILE.write_bytes(key)
    os.chmod(LOG_KEY_FILE, 0o600)
    return key
