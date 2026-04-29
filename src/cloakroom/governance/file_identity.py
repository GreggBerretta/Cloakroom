"""Audit-safe file reference helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any

_PATH_FIELD_KEYS = frozenset(
    {
        "file_path",
        "input_path",
        "output_path",
        "anonymized_path",
    }
)
_SAFE_EXT_RE = re.compile(r"[^a-z0-9]+")


def build_safe_file_reference(
    file_path: str | Path | None,
    *,
    file_hash: str = "",
    file_ext: str = "",
) -> dict[str, str]:
    """Return a non-PII file reference for reports and audit events."""
    path_text = str(file_path or "").strip()
    normalized_ext = _normalize_file_ext(file_ext, path_text)
    digest = _normalize_digest(file_hash) or _hash_file_identity(path_text)
    label = _safe_file_label(path_text, normalized_ext, digest)
    return {
        "file_hash": digest,
        "file_label_safe": label,
    }


def scrub_file_references(value: Any) -> Any:
    """Replace raw path-shaped fields with opaque hashes and safe labels."""
    if isinstance(value, list):
        return [scrub_file_references(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_file_references(item) for item in value)
    if not isinstance(value, dict):
        return value

    out: dict[str, Any] = {}
    file_hash_hint = str(value.get("file_hash") or value.get("file_hash_before") or "")
    file_ext_hint = str(value.get("file_ext") or "")

    for key, item in value.items():
        key_text = str(key)
        if key_text in _PATH_FIELD_KEYS:
            ref = build_safe_file_reference(
                item,
                file_hash=file_hash_hint,
                file_ext=file_ext_hint,
            )
            if key_text == "file_path":
                out.update(ref)
            else:
                prefix = key_text[: -len("_path")]
                out[f"{prefix}_hash"] = ref["file_hash"]
                out[f"{prefix}_label_safe"] = ref["file_label_safe"]
            continue
        out[key_text] = scrub_file_references(item)

    return out


def _normalize_digest(file_hash: str) -> str:
    digest = str(file_hash or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{32,128}", digest):
        return digest
    return ""


def _hash_file_identity(file_path: str) -> str:
    material = file_path or "<unknown-file>"
    return hashlib.sha256(f"cloakroom-file-ref:{material}".encode("utf-8")).hexdigest()


def _normalize_file_ext(file_ext: str, file_path: str) -> str:
    ext = str(file_ext or "").strip().lower()
    if not ext and file_path and not _is_clipboard_ref(file_path):
        ext = Path(file_path).suffix.lower()
    if ext == "clipboard" or _is_clipboard_ref(file_path):
        return "clipboard"
    ext = ext.lstrip(".")
    ext = _SAFE_EXT_RE.sub("", ext)
    return ext[:16] or "file"


def _safe_file_label(file_path: str, file_ext: str, file_hash: str) -> str:
    if _is_clipboard_ref(file_path) or file_ext == "clipboard":
        return "clipboard"
    return f"{file_ext}:{file_hash[:12]}"


def _is_clipboard_ref(file_path: str) -> bool:
    return str(file_path or "").strip().lower() in {"<clipboard>", "clipboard"}
