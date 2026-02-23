"""PII/token-safe log sanitization helpers."""

from __future__ import annotations

import re
from typing import Any

from cowork_shield.tokenizer.patterns import ANY_TOKEN_PATTERN

REDACTION_TOKEN = "[REDACTED]"
SENSITIVE_KEYS = {
    "passphrase",
    "password",
    "token_mappings",
    "vault_contents",
    "master_key",
    "derived_key",
    "clipboard_text",
    "clipboard_content",
    "payload",
}

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"\b(?:\+?\d{1,3}[\s().-]*)?(?:\d[\s().-]*){7,14}\d\b"
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_PASSPHRASE_INLINE_RE = re.compile(
    r"(?i)\b(passphrase|password)\s*[:=]\s*[^\s,;]+"
)
_PERSONISH_RE = re.compile(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b")


def sanitize_text(text: str) -> tuple[str, bool]:
    """Redact sensitive patterns from text."""
    if not text:
        return text, False

    value = text
    changed = False
    patterns = (
        _EMAIL_RE,
        _PHONE_RE,
        _SSN_RE,
        _CARD_RE,
        _PASSPHRASE_INLINE_RE,
        ANY_TOKEN_PATTERN,
        _PERSONISH_RE,
    )
    for pattern in patterns:
        next_value = pattern.sub(REDACTION_TOKEN, value)
        if next_value != value:
            changed = True
            value = next_value
    return value, changed


def sanitize_value(value: Any) -> tuple[Any, bool]:
    """Recursively sanitize nested values before logging."""
    if value is None:
        return None, False
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        changed = False
        out = []
        for item in value:
            sanitized, item_changed = sanitize_value(item)
            changed = changed or item_changed
            out.append(sanitized)
        return out, changed
    if isinstance(value, tuple):
        changed = False
        out = []
        for item in value:
            sanitized, item_changed = sanitize_value(item)
            changed = changed or item_changed
            out.append(sanitized)
        return tuple(out), changed
    if isinstance(value, dict):
        changed = False
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in SENSITIVE_KEYS:
                out[str(key)] = REDACTION_TOKEN
                changed = True
                continue
            sanitized, item_changed = sanitize_value(item)
            out[str(key)] = sanitized
            changed = changed or item_changed
        return out, changed
    return value, False


def sanitize_exception(exc: Exception, *, debug: bool = False) -> dict[str, Any]:
    """Return sanitized exception payload with no sensitive values."""
    message, changed = sanitize_text(str(exc))
    payload: dict[str, Any] = {
        "type": exc.__class__.__name__,
        "message": message,
    }
    if debug:
        import traceback

        tb_text, tb_changed = sanitize_text("".join(traceback.format_exception_only(type(exc), exc)))
        payload["trace"] = tb_text
        changed = changed or tb_changed
    payload["sanitized"] = changed
    return payload

