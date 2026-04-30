"""Clipboard shield/restore operations."""

from cloakroom.clipboard.operations import (
    ClipboardRestoreResult,
    ClipboardShieldResult,
    restore_clipboard,
    restore_clipboard_text,
    shield_clipboard,
    shield_clipboard_text,
)

__all__ = [
    "ClipboardShieldResult",
    "ClipboardRestoreResult",
    "shield_clipboard",
    "shield_clipboard_text",
    "restore_clipboard",
    "restore_clipboard_text",
]
