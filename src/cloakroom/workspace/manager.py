"""Workspace lifecycle management and multi-file identity sharing."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import getpass
import json
import os
from pathlib import Path
import shutil
import threading
import uuid
from dataclasses import dataclass, field
import logging as py_logging

from cloakroom.exceptions import BackupError, WorkspaceExpiredError, WorkspaceNotFoundError
from cloakroom.logging import append_audit_event, log_event
from cloakroom.logging.audit import audit_log_path_for_workspace_dir
from cloakroom.models import VaultData, now_iso
from cloakroom.tokenizer.generator import TokenGenerator
from cloakroom.vault.crypto import derive_hmac_key, generate_master_key
from cloakroom.vault.keychain import (
    delete_master_key,
    get_master_key,
    store_master_key,
)
from cloakroom.vault.vault import Vault

BASE_DIR = Path.home() / ".cloakroom" / "workspaces"
BACKUP_BASE_DIR = Path.home() / ".cloakroom" / "backups"


@dataclass
class WorkspaceContext:
    """A loaded workspace ready for pipeline operations.

    Holds the loaded vault data, token generator (with restored state),
    and provides methods to persist changes back to the vault.
    """

    workspace_id: str
    workspace_name: str
    vault: Vault
    vault_data: VaultData
    token_generator: TokenGenerator
    master_key: bytes
    _operation_lock: threading.RLock = field(
        default_factory=threading.RLock,
        repr=False,
        compare=False,
    )

    def persist(self) -> None:
        """Save current state (mappings, counters) back to vault."""
        counters, mappings = self.token_generator.export_state()
        self.vault_data.token_counter = counters
        self.vault_data.mappings = mappings
        self.vault.save(self.vault_data, self.master_key)

    def get_reverse_lookup(self) -> dict[str, str]:
        """Build token_text -> original_value lookup for restoration."""
        return self.token_generator.get_reverse_lookup()

    @contextmanager
    def operation_lock(self):
        """Serialize workspace operations to avoid concurrent state corruption."""
        with self._operation_lock:
            yield

    def ensure_not_expired(self) -> None:
        """Fail fast when TTL has elapsed during an active session."""
        ttl_hours = self.vault_data.ttl_hours
        if ttl_hours <= 0:
            return

        created = datetime.fromisoformat(self.vault_data.created_at)
        elapsed_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        if elapsed_hours > ttl_hours:
            raise WorkspaceExpiredError(self.workspace_name)


class WorkspaceManager:
    """Manages workspace lifecycle and multi-file identity sharing."""

    def __init__(self, base_dir: Path | None = None):
        self._base_dir = base_dir or BASE_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def create_workspace(
        self, name: str, ttl_hours: int = 24
    ) -> WorkspaceContext:
        """Create a new workspace with fresh encryption keys."""
        workspace_id = str(uuid.uuid4())
        ws_dir = self._base_dir / name
        ws_dir.mkdir(parents=True, exist_ok=True)

        # Generate and store master key
        master_key = generate_master_key()
        store_master_key(workspace_id, master_key)

        # Write workspace metadata
        metadata = {
            "workspace_id": workspace_id,
            "workspace_name": name,
            "vault_path": str(ws_dir / "vault.enc"),
        }
        (ws_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        # Create initial vault data
        vault = Vault(ws_dir / "vault.enc")
        vault_data = VaultData(
            workspace_id=workspace_id,
            workspace_name=name,
            created_at=now_iso(),
            updated_at=now_iso(),
            ttl_hours=ttl_hours,
        )
        vault.save(vault_data, master_key)

        # Initialize token generator
        hmac_key = derive_hmac_key(master_key)
        token_gen = TokenGenerator(hmac_key)

        ctx = WorkspaceContext(
            workspace_id=workspace_id,
            workspace_name=name,
            vault=vault,
            vault_data=vault_data,
            token_generator=token_gen,
            master_key=master_key,
        )
        log_event(
            "engine",
            py_logging.INFO,
            "workspace_created",
            "Workspace created",
            workspace_id=workspace_id,
            metadata={"workspace_name": name, "ttl_hours": ttl_hours},
        )
        append_audit_event(
            ctx,
            event="workspace_created",
            fields={"ttl_hours": ttl_hours, "user": getpass.getuser()},
        )
        return ctx

    def get_or_create_workspace(
        self, name: str, ttl_hours: int = 24
    ) -> WorkspaceContext:
        """Load an existing workspace or create a new one."""
        ws_dir = self._base_dir / name
        meta_path = ws_dir / "metadata.json"

        if meta_path.exists():
            return self.get_active_workspace(name)
        return self.create_workspace(name, ttl_hours)

    def get_active_workspace(self, name: str) -> WorkspaceContext:
        """Load a workspace, returning a context object for pipeline use."""
        ws_dir = self._base_dir / name
        meta_path = ws_dir / "metadata.json"

        if not meta_path.exists():
            raise WorkspaceNotFoundError(name)

        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        workspace_id = metadata["workspace_id"]

        # Retrieve master key from Keychain
        master_key = get_master_key(workspace_id)
        if master_key is None:
            raise WorkspaceNotFoundError(
                f"Encryption key for workspace '{name}' not found in Keychain. "
                f"The vault cannot be decrypted. If this Keychain entry was deleted, "
                f"the workspace is cryptographically unrecoverable."
            )

        # Load vault
        vault = Vault(Path(metadata["vault_path"]))
        vault_data = vault.load(master_key)

        # Restore token generator state
        hmac_key = derive_hmac_key(master_key)
        token_gen = TokenGenerator(hmac_key)
        token_gen.load_state(vault_data.token_counter, vault_data.mappings)

        return WorkspaceContext(
            workspace_id=workspace_id,
            workspace_name=name,
            vault=vault,
            vault_data=vault_data,
            token_generator=token_gen,
            master_key=master_key,
        )

    def get_workspace_metadata(self, name: str) -> dict:
        """Load workspace metadata without requiring Keychain access."""
        ws_dir = self._base_dir / name
        meta_path = ws_dir / "metadata.json"
        if not meta_path.exists():
            raise WorkspaceNotFoundError(name)
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def get_workspace_dir(self, name: str) -> Path:
        """Return the workspace directory path."""
        ws_dir = self._base_dir / name
        if not (ws_dir / "metadata.json").exists():
            raise WorkspaceNotFoundError(name)
        return ws_dir

    def get_audit_log_path(self, name: str) -> Path:
        """Return expected audit log path for a workspace."""
        ws_dir = self.get_workspace_dir(name)
        return audit_log_path_for_workspace_dir(ws_dir)

    def list_workspaces(self) -> list[dict]:
        """List all workspaces with metadata."""
        workspaces = []
        if not self._base_dir.exists():
            return workspaces

        for ws_dir in sorted(self._base_dir.iterdir()):
            meta_path = ws_dir / "metadata.json"
            if not meta_path.exists():
                continue

            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            workspace_id = metadata["workspace_id"]

            # Try to load vault for status info
            status = "active"
            mappings_count = 0
            files_count = 0

            master_key = get_master_key(workspace_id)
            if master_key is None:
                status = "key_missing"
            else:
                vault = Vault(Path(metadata["vault_path"]))
                try:
                    vault_data = vault.load(master_key)
                    mappings_count = len(vault_data.mappings)
                    files_count = len(vault_data.file_records)
                except Exception:
                    status = "expired_or_corrupted"

            workspaces.append({
                "name": metadata["workspace_name"],
                "workspace_id": workspace_id,
                "status": status,
                "mappings": mappings_count,
                "files": files_count,
                "path": str(ws_dir),
            })

        return workspaces

    def delete_workspace(self, name: str) -> None:
        """Destroy workspace: delete vault, Keychain entry, and directory."""
        ws_dir = self._base_dir / name
        meta_path = ws_dir / "metadata.json"

        if not meta_path.exists():
            raise WorkspaceNotFoundError(name)

        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        workspace_id = metadata["workspace_id"]

        # Delete Keychain entry
        delete_master_key(workspace_id)

        # Delete vault file
        vault_path = Path(metadata["vault_path"])
        if vault_path.exists():
            vault_path.unlink()

        # Delete metadata
        meta_path.unlink()

        # Delete audit log if present
        audit_path = audit_log_path_for_workspace_dir(ws_dir)
        if audit_path.exists():
            audit_path.unlink()

        # Remove directory if empty
        try:
            ws_dir.rmdir()
        except OSError:
            pass

    def close_workspace(self, name: str) -> Path:
        """Create a one-time encrypted local vault backup on explicit close."""
        metadata = self.get_workspace_metadata(name)
        workspace_id = metadata["workspace_id"]
        vault_path = Path(metadata["vault_path"])
        if not vault_path.exists():
            raise BackupError(f"Vault file not found for workspace '{name}': {vault_path}")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = BACKUP_BASE_DIR / workspace_id
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"vault-{timestamp}.enc"
        manifest_path = backup_dir / f"vault-{timestamp}.json"

        shutil.copy2(vault_path, backup_path)
        os.chmod(backup_path, 0o600)

        ttl_hours = 0
        expires_at = ""
        try:
            ctx = self.get_active_workspace(name)
            ttl_hours = int(ctx.vault_data.ttl_hours)
            if ttl_hours > 0:
                expiry = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
                expires_at = expiry.isoformat()
            append_audit_event(
                ctx,
                event="workspace_backup_created",
                fields={
                    "user": getpass.getuser(),
                    "backup_path": str(backup_path),
                    "ttl_hours": ttl_hours,
                },
            )
        except Exception:
            # Backup must still succeed even if Keychain is unavailable.
            pass

        manifest = {
            "workspace_id": workspace_id,
            "workspace_name": name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ttl_hours": ttl_hours,
            "expires_at": expires_at,
            "vault_backup_path": str(backup_path),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        os.chmod(manifest_path, 0o600)

        return backup_path

    def recover_workspace(self, name: str, backup_path: Path | str) -> WorkspaceContext:
        """Recover vault mappings from an explicit backup file."""
        metadata = self.get_workspace_metadata(name)
        workspace_id = metadata["workspace_id"]
        vault_path = Path(metadata["vault_path"])
        source = Path(backup_path).expanduser().resolve()
        if not source.exists():
            raise BackupError(f"Backup path does not exist: {source}")

        raw = source.read_bytes()
        tmp_path = vault_path.with_suffix(vault_path.suffix + ".recover.tmp")
        tmp_path.write_bytes(raw)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, vault_path)
        os.chmod(vault_path, 0o600)

        ctx = self.get_active_workspace(name)
        append_audit_event(
            ctx,
            event="workspace_recovered",
            fields={
                "user": getpass.getuser(),
                "backup_path": str(source),
                "workspace_id": workspace_id,
            },
        )
        return ctx

    def purge_workspace(self, name: str) -> Path:
        """Purge vault mappings after creating a mandatory backup snapshot."""
        backup_path = self.close_workspace(name)
        ctx = self.get_active_workspace(name)
        ctx.token_generator.load_state({}, {})
        ctx.vault_data.mappings = {}
        ctx.vault_data.token_counter = {}
        ctx.vault_data.file_records = []
        ctx.vault_data.anonymize_count = 0
        ctx.vault_data.restore_count = 0
        ctx.vault_data.abort_count = 0
        ctx.vault_data.last_used = now_iso()
        ctx.persist()
        append_audit_event(
            ctx,
            event="workspace_purged",
            fields={
                "user": getpass.getuser(),
                "backup_path": str(backup_path),
            },
        )
        return backup_path

    def set_self_destruct_on_restore(self, name: str, enabled: bool) -> WorkspaceContext:
        """Enable or disable self-destruct-on-restore governance policy."""
        ctx = self.get_active_workspace(name)
        ctx.vault_data.self_destruct_on_restore = bool(enabled)
        ctx.persist()
        append_audit_event(
            ctx,
            event="workspace_governance_updated",
            fields={
                "user": getpass.getuser(),
                "self_destruct_on_restore": bool(enabled),
            },
        )
        return ctx

    def cleanup_expired(self) -> int:
        """Delete all expired workspaces. Returns count deleted."""
        count = 0
        for ws_info in self.list_workspaces():
            if ws_info["status"] == "expired_or_corrupted":
                try:
                    self.delete_workspace(ws_info["name"])
                    count += 1
                except Exception:
                    pass
        return count
