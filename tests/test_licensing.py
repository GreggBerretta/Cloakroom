"""Tests for local license policy enforcement."""

from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from cloakroom import licensing
from cloakroom.exceptions import (
    LicenseFeatureError,
    LicenseKeyInvalidError,
    LicenseLimitExceededError,
)


def test_resolve_license_context_free():
    ctx = licensing.resolve_license_context({})
    assert ctx.tier == "FREE"
    assert not ctx.key_present


def test_resolve_license_context_pro():
    ctx = licensing.resolve_license_context({"license_key": "pro_1234567890ABCDEF"})
    assert ctx.tier == "PRO"
    assert ctx.key_present
    assert ctx.key_fingerprint


def test_invalid_license_key_rejected():
    with pytest.raises(LicenseKeyInvalidError):
        licensing.resolve_license_context({"license_key": "bad"})


def test_column_selective_requires_pro():
    ctx = licensing.resolve_license_context({})
    with pytest.raises(LicenseFeatureError):
        licensing.enforce_license_policy(
            "ANONYMIZE_FILE",
            {"columns": ["A"]},
            license_context=ctx,
        )


def test_free_restore_quota(tmp_path, monkeypatch):
    monkeypatch.setattr(licensing, "LICENSE_USAGE_PATH", tmp_path / "usage.json")
    ctx = licensing.resolve_license_context({})

    for _ in range(licensing.FREE_RESTORE_DAILY_LIMIT):
        usage = licensing.enforce_license_policy(
            "RESTORE_FILE",
            {},
            license_context=ctx,
        )
        assert usage["tier"] == "FREE"

    with pytest.raises(LicenseLimitExceededError):
        licensing.enforce_license_policy(
            "RESTORE_FILE",
            {},
            license_context=ctx,
        )


def test_long_ttl_requires_pro():
    ctx = licensing.resolve_license_context({})
    with pytest.raises(LicenseFeatureError):
        licensing.enforce_license_policy(
            "WORKSPACE_SWITCH",
            {"ttl_hours": licensing.FREE_MAX_TTL_HOURS + 1},
            license_context=ctx,
        )


def test_advanced_hebrew_requires_pro():
    ctx = licensing.resolve_license_context({})
    with pytest.raises(LicenseFeatureError):
        licensing.enforce_license_policy(
            "ANONYMIZE_FILE",
            {"hebrew_backend": "transformers"},
            license_context=ctx,
        )


def test_restore_quota_counter_is_utc_day_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(licensing, "LICENSE_USAGE_PATH", tmp_path / "usage.json")
    ctx = licensing.resolve_license_context({})
    usage = licensing.enforce_license_policy("RESTORE_FILE", {}, license_context=ctx)
    assert usage["free_daily_restores_used"] == 1

    today = datetime.now(timezone.utc).date().isoformat()
    payload = json.loads((tmp_path / "usage.json").read_text(encoding="utf-8"))
    assert payload["free_restore_counts"][today] == 1
