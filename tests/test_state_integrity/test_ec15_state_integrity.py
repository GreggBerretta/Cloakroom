"""EC-15 State Integrity & Recovery test harness (release-blocking)."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import threading
import time

import pytest

from cloakroom.clipboard import operations as clipboard_ops
from cloakroom.exceptions import (
    HallucinationDetectedError,
    IncompleteRestorationError,
    IntegrityError,
    WorkspaceExpiredError,
)
from cloakroom.models import (
    DetectedEntity,
    EntityMapping,
    EntityType,
    Token,
    VaultData,
    now_iso,
)
from cloakroom.logging import append_audit_event
from cloakroom.logging import config as log_config
from cloakroom.logging.audit import read_audit_events
from cloakroom.logging.config import configure_logging, log_event
from cloakroom.pipeline.anonymize import AnonymizePipeline
from cloakroom.pipeline.restore import RestorePipeline
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.vault import Vault
from cloakroom.workspace.manager import WorkspaceContext


class FakeDetectionEngine:
    """Deterministic detector used for integrity tests."""

    model_lock_key = "en_core_web_lg"

    def __init__(self, score_threshold: float = 0.7):  # noqa: ARG002
        self._model_hash = "ec15-model-hash"

    def get_model_hash(self) -> str:
        return self._model_hash

    def detect_in_cell(self, text: str, source_id: str) -> list[DetectedEntity]:
        needles = [
            ("John Smith", EntityType.PERSON),
            ("Acme Corp", EntityType.ORGANIZATION),
        ]

        entities: list[DetectedEntity] = []
        for needle, entity_type in needles:
            start = 0
            while True:
                idx = text.find(needle, start)
                if idx < 0:
                    break
                entities.append(
                    DetectedEntity(
                        entity_type=entity_type,
                        text=needle,
                        start=idx,
                        end=idx + len(needle),
                        score=0.99,
                        source_id=source_id,
                    )
                )
                start = idx + len(needle)
        entities.sort(key=lambda e: e.start)
        return entities


@pytest.fixture
def workspace_ctx(tmp_path):
    master_key = generate_master_key()
    hmac_key = derive_hmac_key(master_key)
    vault_path = tmp_path / "vault.enc"
    vault = Vault(vault_path)
    vault_data = VaultData(
        workspace_id="ec15-id",
        workspace_name="ec15-workspace",
        created_at=now_iso(),
        updated_at=now_iso(),
        ttl_hours=168,
    )
    token_gen = TokenGenerator(hmac_key)
    return WorkspaceContext(
        workspace_id="ec15-id",
        workspace_name="ec15-workspace",
        vault=vault,
        vault_data=vault_data,
        token_generator=token_gen,
        master_key=master_key,
    )


def _anonymize_text(
    workspace_ctx: WorkspaceContext,
    tmp_path,
    *,
    filename: str,
    text: str = "John Smith works at Acme Corp.",
):
    input_path = tmp_path / filename
    output_path = tmp_path / f"{input_path.stem}.anonymized{input_path.suffix}"
    input_path.write_text(text, encoding="utf-8")

    pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
    pipeline._detection = FakeDetectionEngine()  # deterministic test detector
    result = pipeline.run(input_path, output_path)
    return input_path, output_path, result


class TestEC15CrashConsistency:
    def test_t_crash_001_kill_during_anonymize(self, workspace_ctx, tmp_path, monkeypatch):
        input_path = tmp_path / "crash001.txt"
        output_path = tmp_path / "crash001.anonymized.txt"
        input_path.write_text("John Smith", encoding="utf-8")

        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        pipeline._detection = FakeDetectionEngine()

        def crash_persist():
            raise RuntimeError("simulated SIGKILL during vault commit")

        monkeypatch.setattr(workspace_ctx, "persist", crash_persist)

        with pytest.raises(RuntimeError, match="simulated SIGKILL"):
            pipeline.run(input_path, output_path)

        # No partially committed anonymized file; workspace state rolled back.
        assert not output_path.exists()
        assert workspace_ctx.vault_data.file_records == []
        assert workspace_ctx.token_generator.get_all_mappings() == {}

    def test_t_crash_002_kill_during_restore(self, workspace_ctx, tmp_path, monkeypatch):
        _input, anonymized_path, _result = _anonymize_text(
            workspace_ctx,
            tmp_path,
            filename="crash002.txt",
        )
        restore_path = tmp_path / "crash002.restored.txt"
        temp_path = restore_path.with_suffix(".txt.tmp")

        def crash_rename(_src, _dst):
            raise RuntimeError("simulated SIGKILL before commit rename")

        monkeypatch.setattr("cloakroom.pipeline.restore.os.rename", crash_rename)

        pipeline = RestorePipeline(workspace_ctx)
        with pytest.raises(RuntimeError, match="simulated SIGKILL"):
            pipeline.run(anonymized_path, restore_path)

        # No partial committed output.
        assert anonymized_path.exists()
        assert not restore_path.exists()
        assert not temp_path.exists()

    def test_t_crash_003_kill_during_vault_write(self, workspace_ctx, monkeypatch):
        # Persist a known baseline snapshot first.
        workspace_ctx.vault_data.anonymize_count = 1
        workspace_ctx.persist()
        baseline = workspace_ctx.vault.load(workspace_ctx.master_key)

        workspace_ctx.vault_data.anonymize_count = 999

        def crash_atomic_write(_path, _data):
            raise OSError("simulated kill during atomic write")

        monkeypatch.setattr("cloakroom.vault.vault.atomic_write", crash_atomic_write)

        with pytest.raises(OSError, match="simulated kill"):
            workspace_ctx.vault.save(workspace_ctx.vault_data, workspace_ctx.master_key)

        after = workspace_ctx.vault.load(workspace_ctx.master_key)
        assert after.anonymize_count == baseline.anonymize_count


class TestEC15FilesystemHostility:
    def test_t_fs_001_file_renamed_between_anonymize_and_restore(self, workspace_ctx, tmp_path):
        original_text = "John Smith works at Acme Corp."
        _input, anonymized_path, _result = _anonymize_text(
            workspace_ctx,
            tmp_path,
            filename="fs001.txt",
            text=original_text,
        )
        renamed_path = tmp_path / "renamed.anonymized.txt"
        anonymized_path.rename(renamed_path)

        restore_path = tmp_path / "fs001.restored.txt"
        restored = RestorePipeline(workspace_ctx).run(renamed_path, restore_path)
        assert restored.verification_passed
        assert restore_path.read_text(encoding="utf-8") == original_text

    def test_t_fs_002_file_moved_across_directories(self, workspace_ctx, tmp_path):
        original_text = "John Smith works at Acme Corp."
        _input, anonymized_path, _result = _anonymize_text(
            workspace_ctx,
            tmp_path,
            filename="fs002.txt",
            text=original_text,
        )
        moved_dir = tmp_path / "nested" / "deeper"
        moved_dir.mkdir(parents=True)
        moved_path = moved_dir / anonymized_path.name
        anonymized_path.rename(moved_path)

        restore_path = tmp_path / "fs002.restored.txt"
        restored = RestorePipeline(workspace_ctx).run(moved_path, restore_path)
        assert restored.verification_passed
        assert restore_path.read_text(encoding="utf-8") == original_text

    def test_t_fs_003_encoding_rewrite(self, workspace_ctx, tmp_path):
        _input, anonymized_path, _result = _anonymize_text(
            workspace_ctx,
            tmp_path,
            filename="fs003.txt",
        )
        anonymized_text = anonymized_path.read_text(encoding="utf-8")
        utf16_crlf = anonymized_text.replace("\n", "\r\n").encode("utf-16")
        anonymized_path.write_bytes(utf16_crlf)

        restore_path = tmp_path / "fs003.restored.txt"
        pipeline = RestorePipeline(workspace_ctx)
        try:
            pipeline.run(anonymized_path, restore_path)
        except (HallucinationDetectedError, IncompleteRestorationError, IntegrityError):
            # Explicit fail-closed is acceptable for hostile re-encoding.
            assert not restore_path.exists()
        else:
            # If it succeeds, it must be complete and explicit.
            assert restore_path.exists()
            assert "John Smith" in restore_path.read_text(encoding="utf-8", errors="replace")


class TestEC15ConcurrencySafety:
    def test_t_conc_001_two_restores_simultaneously(self, workspace_ctx, tmp_path):
        original_text = "John Smith works at Acme Corp."
        _input, anonymized_path, _result = _anonymize_text(
            workspace_ctx,
            tmp_path,
            filename="conc001.txt",
            text=original_text,
        )

        barrier = threading.Barrier(2)

        def _restore(idx: int):
            barrier.wait()
            restore_path = tmp_path / f"conc001.restored.{idx}.txt"
            result = RestorePipeline(workspace_ctx).run(anonymized_path, restore_path)
            return result, restore_path

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_restore, idx) for idx in (1, 2)]
            results = [future.result() for future in futures]

        assert workspace_ctx.vault_data.restore_count >= 2
        for result, restore_path in results:
            assert result.verification_passed
            assert restore_path.read_text(encoding="utf-8") == original_text

    def test_t_conc_002_clipboard_hotkey_spam(self, workspace_ctx, monkeypatch):
        monkeypatch.setattr(clipboard_ops, "DetectionEngine", FakeDetectionEngine)

        values = deque([f"John Smith batch {i}" for i in range(20)])
        outputs: list[str] = []
        io_lock = threading.Lock()

        def fake_run(cmd, check, capture_output, text, input=None):  # noqa: A002, ARG001
            with io_lock:
                if cmd[0] == "pbpaste":
                    payload = values.popleft() if values else "John Smith"
                    return type("CP", (), {"stdout": payload})()
                if cmd[0] == "pbcopy":
                    outputs.append(input or "")
                    return type("CP", (), {"stdout": ""})()
            raise AssertionError(f"Unexpected command: {cmd}")

        monkeypatch.setattr(clipboard_ops.subprocess, "run", fake_run)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(clipboard_ops.shield_clipboard, workspace_ctx, score_threshold=0.5)
                for _ in range(20)
            ]
            _ = [future.result() for future in futures]

        assert len(outputs) == 20
        assert all("[PERSON_" in value for value in outputs)
        assert all("John Smith" not in value for value in outputs)


class TestEC15VaultIntegrity:
    def test_t_vault_001_corrupt_mapping_segment(self, workspace_ctx, tmp_path):
        _input, anonymized_path, _result = _anonymize_text(
            workspace_ctx,
            tmp_path,
            filename="vault001.txt",
        )

        counters, mappings = workspace_ctx.token_generator.export_state()
        mapping_key = next(iter(mappings))
        mapping = mappings[mapping_key]
        mappings[mapping_key] = EntityMapping(
            token=Token(
                token_text=mapping.token.token_text,
                entity_type=mapping.token.entity_type,
                hmac_tag="tampered-hmac",
            ),
            original_value=mapping.original_value,
            normalized_key=mapping.normalized_key,
            entity_type=mapping.entity_type,
            first_seen=mapping.first_seen,
            source_files=mapping.source_files,
        )
        workspace_ctx.token_generator.load_state(counters, mappings)

        with pytest.raises(IntegrityError, match="HMAC verification failed"):
            RestorePipeline(workspace_ctx).run(anonymized_path, tmp_path / "vault001.restored.txt")

    def test_t_vault_002_partial_metadata_deletion(self, workspace_ctx, tmp_path):
        original_text = "John Smith works at Acme Corp."
        _input, anonymized_path, _result = _anonymize_text(
            workspace_ctx,
            tmp_path,
            filename="vault002.txt",
            text=original_text,
        )

        vault_dict = workspace_ctx.vault_data.to_dict()
        for key in [
            "trust_flip_responses",
            "rewrite_avoidance_responses",
            "pre_llm_capture_responses",
            "time_to_close_after_restore",
        ]:
            vault_dict.pop(key, None)

        migrated = VaultData.from_dict(vault_dict)
        workspace_ctx.vault_data = migrated
        workspace_ctx.token_generator.load_state(migrated.token_counter, migrated.mappings)

        restore_path = tmp_path / "vault002.restored.txt"
        result = RestorePipeline(workspace_ctx).run(anonymized_path, restore_path)
        assert result.verification_passed
        assert restore_path.read_text(encoding="utf-8") == original_text

    def test_t_vault_003_ttl_expiry_during_active_session(self, workspace_ctx, tmp_path):
        workspace_ctx.vault_data.created_at = (
            datetime.now(timezone.utc) - timedelta(hours=48)
        ).isoformat()
        workspace_ctx.vault_data.ttl_hours = 1

        input_path = tmp_path / "ttl003.txt"
        output_path = tmp_path / "ttl003.anonymized.txt"
        input_path.write_text("John Smith", encoding="utf-8")

        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        pipeline._detection = FakeDetectionEngine()

        with pytest.raises(WorkspaceExpiredError):
            pipeline.run(input_path, output_path)


class TestEC15EnvironmentEdges:
    def test_t_env_001_sleep_wake_interruption_no_partial_commit(
        self, workspace_ctx, tmp_path, monkeypatch
    ):
        _input, anonymized_path, _result = _anonymize_text(
            workspace_ctx,
            tmp_path,
            filename="env001.txt",
        )
        restore_path = tmp_path / "env001.restored.txt"

        def interrupted_restore(_self, _input, temp_path, _lookup):
            temp_path.write_text("partial", encoding="utf-8")
            raise RuntimeError("simulated sleep/wake interruption")

        monkeypatch.setattr("cloakroom.handlers.text_handler.TextHandler.restore", interrupted_restore)

        with pytest.raises(RuntimeError, match="sleep/wake"):
            RestorePipeline(workspace_ctx).run(anonymized_path, restore_path)

        assert not restore_path.exists()
        assert not restore_path.with_suffix(".txt.tmp").exists()

    def test_t_env_002_clock_skew_bounds(self, workspace_ctx):
        # Backward skew (future created_at) should not prematurely expire.
        workspace_ctx.vault_data.created_at = (
            datetime.now(timezone.utc) + timedelta(hours=24)
        ).isoformat()
        workspace_ctx.vault_data.ttl_hours = 1
        workspace_ctx.ensure_not_expired()

        # Forward skew beyond TTL should explicitly expire.
        workspace_ctx.vault_data.created_at = (
            datetime.now(timezone.utc) - timedelta(hours=26)
        ).isoformat()
        workspace_ctx.vault_data.ttl_hours = 24
        with pytest.raises(WorkspaceExpiredError):
            workspace_ctx.ensure_not_expired()

    def test_t_env_003_disk_full_during_write_rolls_back(
        self, workspace_ctx, tmp_path, monkeypatch
    ):
        input_path = tmp_path / "env003.txt"
        output_path = tmp_path / "env003.anonymized.txt"
        input_path.write_text("John Smith", encoding="utf-8")

        pipeline = AnonymizePipeline(workspace_ctx, score_threshold=0.5)
        pipeline._detection = FakeDetectionEngine()

        def disk_full():
            raise OSError("No space left on device")

        monkeypatch.setattr(workspace_ctx, "persist", disk_full)

        with pytest.raises(OSError, match="No space left"):
            pipeline.run(input_path, output_path)

        assert not output_path.exists()
        assert workspace_ctx.token_generator.get_all_mappings() == {}
        assert workspace_ctx.vault_data.file_records == []


class TestEC15LogIntegrity:
    def _isolate_logs(self, tmp_path, monkeypatch):
        log_dir = tmp_path / "logs"
        monkeypatch.setattr(log_config, "LOG_DIR", log_dir)
        monkeypatch.setattr(log_config, "LOG_FILE", log_dir / "cloakroom.log")
        monkeypatch.setattr(log_config, "LOG_KEY_FILE", log_dir / ".logkey")
        return log_dir

    def test_t_log_001_log_permissions_0600(self, tmp_path, monkeypatch):
        self._isolate_logs(tmp_path, monkeypatch)
        configure_logging(component="engine", verbose=False, no_logging=False, encrypt_logs=False)
        log_event("engine", logging.INFO, "log_permission_test", "hello")

        mode = os.stat(log_config.LOG_FILE).st_mode & 0o777
        assert mode == 0o600

    def test_t_log_002_log_rotation_retention(self, tmp_path, monkeypatch):
        log_dir = self._isolate_logs(tmp_path, monkeypatch)
        log_dir.mkdir(parents=True, exist_ok=True)
        stale = log_dir / "cloakroom.log.4"
        stale.write_text("{}", encoding="utf-8")
        stale_time = time.time() - (31 * 24 * 3600)
        os.utime(stale, (stale_time, stale_time))

        configure_logging(component="engine", verbose=False, no_logging=False, encrypt_logs=False)
        assert not stale.exists()

    def test_t_log_003_audit_hmac_tamper_detection(self, workspace_ctx, tmp_path):
        append_audit_event(
            workspace_ctx,
            event="integrity_failure",
            fields={"file_path": str(tmp_path / "sample.txt"), "failure_type": "IntegrityError"},
        )
        rows = read_audit_events(workspace_ctx)
        assert rows and rows[0].verified is True

        audit_path = workspace_ctx.vault.path.parent / "audit.log.jsonl"
        payload = audit_path.read_text(encoding="utf-8")
        audit_path.write_text(payload.replace("IntegrityError", "TamperedError"), encoding="utf-8")

        tampered_rows = read_audit_events(workspace_ctx)
        assert tampered_rows and tampered_rows[0].verified is False

    def test_t_log_004_sanitization_redacts_pii(self, tmp_path, monkeypatch):
        self._isolate_logs(tmp_path, monkeypatch)
        configure_logging(component="engine", verbose=False, no_logging=False, encrypt_logs=False)
        log_event(
            "engine",
            logging.INFO,
            "sanitize_test",
            "Contact John Smith at john.smith@acme.com token [PERSON_00001]",
        )

        content = log_config.LOG_FILE.read_text(encoding="utf-8")
        assert "John Smith" not in content
        assert "john.smith@acme.com" not in content
        assert "[PERSON_00001]" not in content
        entries = [json.loads(line) for line in content.splitlines() if line.strip()]
        assert any(entry.get("event") == "log_sanitization_triggered" for entry in entries)
