"""Local license policy checks for wrapper IPC operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any

from cowork_shield.exceptions import (
    LicenseFeatureError,
    LicenseKeyInvalidError,
    LicenseLimitExceededError,
)

FREE_RESTORE_DAILY_LIMIT = 5
FREE_MAX_TTL_HOURS = 168
PRO_TIER = "PRO"
FREE_TIER = "FREE"

LICENSE_USAGE_PATH = Path.home() / ".cowork-shield" / "license_usage.json"
_USAGE_LOCK = threading.Lock()
_PRO_KEY_PATTERN = re.compile(r"^pro_[A-Za-z0-9]{16,}$")
_AUDIT_EXPORT_REQUEST_TYPES = {"AUDIT_EXPORT", "WORKSPACE_EXPORT_AUDIT_SUMMARY"}


@dataclass(frozen=True)
class LicenseContext:
    """Resolved license context for a single request."""

    tier: str
    key_fingerprint: str
    key_present: bool

    @property
    def is_pro(self) -> bool:
        return self.tier == PRO_TIER


def resolve_license_context(payload: dict[str, Any]) -> LicenseContext:
    """Validate and classify a license key from request payload."""
    raw_key = payload.get("license_key", "")
    if raw_key is None:
        raw_key = ""
    if not isinstance(raw_key, str):
        raise LicenseKeyInvalidError("'license_key' must be a string")

    key = raw_key.strip()
    if not key:
        return LicenseContext(tier=FREE_TIER, key_fingerprint="", key_present=False)

    if _is_valid_pro_key(key):
        return LicenseContext(
            tier=PRO_TIER,
            key_fingerprint=hashlib.sha256(key.encode("utf-8")).hexdigest()[:12],
            key_present=True,
        )

    raise LicenseKeyInvalidError("Provided license key is invalid")


def enforce_license_policy(
    request_type: str,
    payload: dict[str, Any],
    *,
    license_context: LicenseContext,
) -> dict[str, Any]:
    """Apply release-gated license checks and return usage metadata."""
    usage: dict[str, Any] = {
        "tier": license_context.tier,
        "free_daily_restore_limit": FREE_RESTORE_DAILY_LIMIT,
    }
    operation = request_type.upper()

    if operation in {"ANONYMIZE_FILE", "CLIPBOARD_ANONYMIZE"}:
        _enforce_pro_features_for_anonymize(payload, license_context=license_context)
    if operation == "WORKSPACE_SWITCH":
        _enforce_ttl_policy(payload, license_context=license_context)
    if operation in _AUDIT_EXPORT_REQUEST_TYPES:
        _require_pro(license_context, feature="audit export")
    if operation in {"RESTORE_FILE", "CLIPBOARD_RESTORE"} and not license_context.is_pro:
        usage["free_daily_restores_used"] = _consume_free_restore_credit()

    return usage


def _enforce_pro_features_for_anonymize(
    payload: dict[str, Any],
    *,
    license_context: LicenseContext,
) -> None:
    columns = payload.get("columns", [])
    has_columns = False
    if isinstance(columns, list):
        has_columns = any(str(value).strip() for value in columns)
    elif isinstance(columns, str):
        has_columns = any(part.strip() for part in columns.split(","))
    elif columns is not None:
        raise LicenseFeatureError("'columns' must be a list or comma-separated string")

    if has_columns:
        _require_pro(license_context, feature="column-selective anonymization")

    backend = payload.get("hebrew_backend", "")
    if backend is None:
        backend = ""
    if not isinstance(backend, str):
        raise LicenseFeatureError("'hebrew_backend' must be a string")
    normalized_backend = backend.strip().lower()
    if normalized_backend in {"stanza", "transformers"}:
        _require_pro(license_context, feature="advanced Hebrew backend")


def _enforce_ttl_policy(payload: dict[str, Any], *, license_context: LicenseContext) -> None:
    ttl_hours_raw = payload.get("ttl_hours", FREE_MAX_TTL_HOURS)
    try:
        ttl_hours = int(ttl_hours_raw)
    except (TypeError, ValueError) as exc:
        raise LicenseFeatureError("'ttl_hours' must be an integer") from exc

    if ttl_hours > FREE_MAX_TTL_HOURS:
        _require_pro(license_context, feature="long TTL workspace")


def _require_pro(license_context: LicenseContext, *, feature: str) -> None:
    if license_context.is_pro:
        return
    raise LicenseFeatureError(f"{feature} requires a valid Pro license key")


def _is_valid_pro_key(key: str) -> bool:
    if _PRO_KEY_PATTERN.match(key):
        return True

    allowed = os.getenv("CWS_PRO_LICENSE_KEYS", "")
    if not allowed.strip():
        return False
    allowed_keys = {item.strip() for item in allowed.split(",") if item.strip()}
    return key in allowed_keys


def _consume_free_restore_credit() -> int:
    """Increment and return today's free-tier restore count."""
    today = datetime.now(timezone.utc).date().isoformat()
    with _USAGE_LOCK:
        usage = _load_usage()
        restore_counts = usage.setdefault("free_restore_counts", {})
        current = int(restore_counts.get(today, 0))
        if current >= FREE_RESTORE_DAILY_LIMIT:
            raise LicenseLimitExceededError(
                f"Free restore quota exceeded ({FREE_RESTORE_DAILY_LIMIT}/day). "
                "Provide a valid Pro license key."
            )
        current += 1
        restore_counts[today] = current
        _save_usage(usage)
        return current


def _load_usage() -> dict[str, Any]:
    if not LICENSE_USAGE_PATH.exists():
        return {}
    try:
        payload = json.loads(LICENSE_USAGE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _save_usage(payload: dict[str, Any]) -> None:
    LICENSE_USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = LICENSE_USAGE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, LICENSE_USAGE_PATH)

