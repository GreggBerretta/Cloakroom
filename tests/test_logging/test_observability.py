"""Logging and audit observability tests."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import time

import pytest

from cloakroom.logging import audit as audit_mod
from cloakroom.logging import config as log_config
from cloakroom.logging.audit import append_audit_event, read_audit_events
from cloakroom.logging.config import (
    collect_log_payload,
    configure_logging,
    delete_log_files,
    export_log_files,
    log_event,
)
from cloakroom.logging.sanitizer import sanitize_text, sanitize_value
from cloakroom.models import VaultData, now_iso
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext


@pytest.fixture
def isolated_logs(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(log_config, "LOG_DIR", log_dir)
    monkeypatch.setattr(log_config, "LOG_FILE", log_dir / "cloakroom.log")
    monkeypatch.setattr(log_config, "LOG_KEY_FILE", log_dir / ".logkey")
    return log_dir


def _make_workspace_context(tmp_path: Path) -> WorkspaceContext:
    master_key = generate_master_key()
    hmac_key = derive_hmac_key(master_key)
    vault_path = tmp_path / "vault.enc"
    vault = Vault(vault_path)
    vault_data = VaultData(
        workspace_id="ws-test",
        workspace_name="ws-test",
        created_at=now_iso(),
        updated_at=now_iso(),
        ttl_hours=168,
    )
    vault.save(vault_data, master_key)
    token_gen = TokenGenerator(hmac_key)
    return WorkspaceContext(
        workspace_id="ws-test",
        workspace_name="ws-test",
        vault=vault,
        vault_data=vault_data,
        token_generator=token_gen,
        master_key=master_key,
    )


def test_sanitizer_redacts_tokens_and_pii():
    text = "Contact John Smith at john.smith@acme.com token [PERSON_00001]"
    sanitized, changed = sanitize_text(text)
    assert changed is True
    assert "John Smith" not in sanitized
    assert "john.smith@acme.com" not in sanitized
    assert "[PERSON_00001]" not in sanitized
    assert "[REDACTED]" in sanitized


def test_sanitizer_redacts_sensitive_keys():
    data = {
        "workspace": "alpha",
        "password": "secret",
        "token_mappings": {"[PERSON_00001]": "John Smith"},
    }
    sanitized, changed = sanitize_value(data)
    assert changed is True
    assert sanitized["workspace"] == "alpha"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["token_mappings"] == "[REDACTED]"


def test_log_file_permissions_and_content_sanitization(isolated_logs):
    configure_logging(component="cli", verbose=False, no_logging=False, encrypt_logs=False)
    log_event(
        "cli",
        logging.INFO,
        "test_log",
        "Email john.smith@acme.com token [PERSON_00001]",
    )
    for handler in logging.getLogger("cloakroom").handlers:
        if hasattr(handler, "flush"):
            handler.flush()

    log_file = log_config.LOG_FILE
    assert log_file.exists()
    mode = os.stat(log_file).st_mode & 0o777
    assert mode == 0o600

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert lines
    payloads = [json.loads(line) for line in lines]
    messages = " ".join(str(item.get("message", "")) for item in payloads)
    assert "john.smith@acme.com" not in messages
    assert "[PERSON_00001]" not in messages
    assert any(item.get("event") == "log_sanitization_triggered" for item in payloads)


def test_log_retention_deletes_old_files(isolated_logs):
    isolated_logs.mkdir(parents=True, exist_ok=True)
    old_file = isolated_logs / "cloakroom.log.5"
    old_file.write_text("{}", encoding="utf-8")
    thirty_one_days_ago = time.time() - (31 * 24 * 3600)
    os.utime(old_file, (thirty_one_days_ago, thirty_one_days_ago))

    configure_logging(component="cli", verbose=False, no_logging=False, encrypt_logs=False)
    assert not old_file.exists()


def test_log_export_and_delete(isolated_logs, tmp_path):
    configure_logging(component="cli", verbose=True, no_logging=False, encrypt_logs=False)
    log_event("cli", logging.INFO, "export_test", "hello world")
    export_path = tmp_path / "logs-export.json"
    result_path = export_log_files(export_path)
    assert result_path.exists()
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert "files" in payload
    assert payload["files"]

    deleted = delete_log_files()
    assert deleted >= 1


def test_collect_log_payload(isolated_logs):
    configure_logging(component="cli", verbose=False, no_logging=False, encrypt_logs=False)
    log_event("cli", logging.INFO, "collect_test", "collect")
    payload = collect_log_payload()
    assert "files" in payload
    assert isinstance(payload["files"], list)


def test_audit_log_hmac_tamper_detection(tmp_path):
    ctx = _make_workspace_context(tmp_path)
    append_audit_event(ctx, event="file_anonymized", fields={"file_path": "/tmp/sample.csv"})

    rows = read_audit_events(ctx)
    assert len(rows) == 1
    assert rows[0].verified is True

    audit_path = audit_mod.audit_log_path_for_workspace_dir(ctx.vault.path.parent)
    original = audit_path.read_text(encoding="utf-8")
    tampered = original.replace("file_anonymized", "file_restored", 1)
    audit_path.write_text(tampered, encoding="utf-8")

    tampered_rows = read_audit_events(ctx)
    assert len(tampered_rows) == 1
    assert tampered_rows[0].verified is False

