"""CLI entry point for CoWork Shield."""

from __future__ import annotations

from datetime import datetime, timezone
import getpass
import json
import logging as py_logging
import os
from pathlib import Path
import stat

import click
from rich.console import Console
from rich.table import Table

from cowork_shield.clipboard.operations import (
    restore_clipboard,
    shield_clipboard,
)
from cowork_shield.detection.engine import HEBREW_BACKEND_CHOICES, LANGUAGE_CHOICES
from cowork_shield.handlers.column_select import parse_columns_option
from cowork_shield.ipc.server import IPCServer
from cowork_shield.ipc.stdio_server import main as stdio_server_main
from cowork_shield.logging import (
    append_audit_event,
    collect_log_payload,
    configure_logging,
    delete_audit_events,
    delete_log_files,
    log_event,
    read_audit_events,
)
from cowork_shield.exceptions import CoWorkShieldError
from cowork_shield.exceptions import WorkspaceNotFoundError
from cowork_shield.pipeline.anonymize import AnonymizePipeline
from cowork_shield.pipeline.columns import inspect_columns
from cowork_shield.pipeline.restore import RestorePipeline
from cowork_shield.vault.keychain import (
    get_master_key,
    store_master_key,
    verify_keychain_permissions,
)
from cowork_shield.vault.recovery import (
    export_encrypted_master_key,
    import_encrypted_master_key,
)
from cowork_shield.workspace.manager import WorkspaceManager

console = Console()
ONBOARDING_MARKER = Path.home() / ".cowork_shield" / ".onboarding_complete"


def _show_error(exc: Exception) -> None:
    code = exc.__class__.__name__
    log_event(
        "cli",
        py_logging.ERROR,
        "command_error",
        "Command failed",
        metadata={"error_code": code},
        exc=exc,
    )
    console.print(f"[bold red]Error [{code}]:[/] {exc}")


def _resolve_passphrase(passphrase: str | None, *, confirm: bool) -> str:
    if passphrase:
        return passphrase
    return click.prompt(
        "Passphrase",
        hide_input=True,
        confirmation_prompt=confirm,
    )


def _workspace_exists(mgr: WorkspaceManager, name: str) -> bool:
    try:
        mgr.get_workspace_metadata(name)
        return True
    except WorkspaceNotFoundError:
        return False


def _get_or_create_workspace_with_warning(
    mgr: WorkspaceManager,
    name: str,
    *,
    ttl_hours: int = 168,
):
    existed = _workspace_exists(mgr, name)
    ctx = mgr.get_or_create_workspace(name, ttl_hours=ttl_hours)
    if not existed:
        console.print(
            "[bold yellow]New workspace created.[/] "
            "Export a recovery key now to avoid irreversible key-loss recovery failure:"
        )
        console.print(
            f"  [dim]cowork-shield workspace export-key --workspace {name} "
            f"--output ~/.cowork_shield/recovery/{name}.recovery.key[/]"
        )
        log_event(
            "cli",
            py_logging.WARNING,
            "workspace_created_recovery_warning",
            "New workspace created; recovery key export recommended",
            workspace_id=ctx.workspace_id,
            metadata={"workspace_name": name},
        )
    return ctx, not existed


def _mark_onboarding_complete(workspace: str) -> None:
    ONBOARDING_MARKER.parent.mkdir(parents=True, exist_ok=True)
    ONBOARDING_MARKER.write_text(
        json.dumps(
            {
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "workspace": workspace,
                "user": getpass.getuser(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    os.chmod(ONBOARDING_MARKER, 0o600)


def _is_onboarding_complete() -> bool:
    return ONBOARDING_MARKER.exists()


@click.group()
@click.option(
    "--verbose",
    is_flag=True,
    help="Enable DEBUG logging (sanitized).",
)
@click.option(
    "--no-logging",
    is_flag=True,
    help="Disable non-audit logs for this process.",
)
@click.option(
    "--encrypt-logs",
    is_flag=True,
    help="Encrypt application logs at rest (optional high-security mode).",
)
@click.version_option(package_name="cowork-shield")
@click.pass_context
def main(ctx, verbose, no_logging, encrypt_logs):
    """CoWork Shield -- Reversible document anonymization for safe LLM usage."""
    configure_logging(
        component="cli",
        verbose=verbose,
        no_logging=no_logging,
        encrypt_logs=encrypt_logs,
    )
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["no_logging"] = no_logging
    ctx.obj["encrypt_logs"] = encrypt_logs
    log_event(
        "cli",
        py_logging.INFO,
        "session_start",
        "CLI session started",
        metadata={
            "verbose": verbose,
            "no_logging": no_logging,
            "encrypt_logs": encrypt_logs,
        },
    )
    if verbose:
        console.print(
            "[bold yellow]DEBUG logging enabled.[/] Logs are sanitized, "
            "but review before sharing externally."
        )
    if not _is_onboarding_complete() and ctx.invoked_subcommand not in {None, "onboarding"}:
        console.print(
            "[bold yellow]First-run onboarding is not complete.[/] "
            "Run [bold]cowork-shield onboarding[/] to create a workspace and export a recovery key."
        )


@main.command("onboarding")
@click.option(
    "-w",
    "--workspace",
    default="default",
    show_default=True,
    help="Workspace to initialize for pilot usage.",
)
@click.option(
    "--ttl",
    type=int,
    default=168,
    show_default=True,
    help="Workspace TTL in hours.",
)
@click.option(
    "--export-key/--no-export-key",
    default=True,
    show_default=True,
    help="Export encrypted recovery key during onboarding.",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    default="",
    help="Recovery key output path (default: ~/.cowork_shield/recovery/<workspace>.recovery.key).",
)
@click.option(
    "--passphrase",
    default=None,
    help="Passphrase for recovery key export (prompted if omitted).",
)
def onboarding_cmd(workspace, ttl, export_key, output_path, passphrase):
    """Run first-run onboarding wizard for pilot users."""
    try:
        mgr = WorkspaceManager()
        ctx, _created = _get_or_create_workspace_with_warning(mgr, workspace, ttl_hours=ttl)
        console.print("[green]Workspace ready.[/]")
        console.print(f"  Workspace: {ctx.workspace_name}")
        console.print(f"  ID:        {ctx.workspace_id}")

        if export_key:
            destination = (
                Path(output_path).expanduser()
                if output_path.strip()
                else Path.home() / ".cowork_shield" / "recovery" / f"{workspace}.recovery.key"
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not click.confirm(
                f"Recovery key output exists at {destination}. Overwrite?", default=False
            ):
                raise click.ClickException("Recovery key export skipped by user.")

            resolved_passphrase = _resolve_passphrase(passphrase, confirm=True)
            payload = export_encrypted_master_key(
                workspace_id=ctx.workspace_id,
                master_key=ctx.master_key,
                passphrase=resolved_passphrase,
            )
            destination.write_bytes(payload)
            destination.chmod(stat.S_IRUSR | stat.S_IWUSR)
            append_audit_event(
                ctx,
                event="key_exported",
                fields={
                    "user": getpass.getuser(),
                    "export_path": str(destination.resolve()),
                },
            )
            console.print("[green]Recovery key exported.[/]")
            console.print(f"  Output: {destination}")
            console.print("  File mode: 600")
            console.print(
                "[bold yellow]Warning:[/] Losing both Keychain entry and recovery key "
                "makes workspace data cryptographically unrecoverable."
            )

        _mark_onboarding_complete(workspace)
        log_event(
            "cli",
            py_logging.INFO,
            "onboarding_complete",
            "Onboarding completed",
            workspace_id=ctx.workspace_id,
            metadata={"workspace_name": workspace, "export_key": bool(export_key)},
        )
        console.print("[green]Onboarding complete.[/]")

    except click.ClickException as e:
        _show_error(e)
        raise SystemExit(1)
    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@main.group("logs")
def logs_group():
    """Export and delete sanitized application logs."""
    pass


@logs_group.command("export")
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(),
    default="",
    help="Destination path for exported log bundle JSON.",
)
@click.option(
    "-w",
    "--workspace",
    "workspace_name",
    default="",
    help="Optional workspace name to include signed audit events.",
)
@click.option(
    "--include-app/--no-include-app",
    default=True,
    show_default=True,
    help="Include rotating non-audit application logs.",
)
@click.option(
    "--include-audit/--no-include-audit",
    default=True,
    show_default=True,
    help="Include signed workspace audit events.",
)
def logs_export(output_path, workspace_name, include_app, include_audit):
    """Export sanitized logs for support/debugging."""
    try:
        if not include_app and not include_audit:
            raise click.UsageError("Select at least one source: --include-app and/or --include-audit.")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if output_path:
            destination = Path(output_path).expanduser().resolve()
        else:
            destination = Path.home() / ".cowork_shield" / "logs" / f"support-export-{timestamp}.json"

        payload: dict[str, object] = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "workspace": workspace_name.strip() or "",
            "include_app": include_app,
            "include_audit": include_audit,
            "app_logs": {},
            "audit_logs": [],
        }

        if include_app:
            payload["app_logs"] = collect_log_payload()

        if include_audit:
            mgr = WorkspaceManager()
            if workspace_name.strip():
                ctx = mgr.get_active_workspace(workspace_name.strip())
                payload["audit_logs"] = [
                    {
                        "workspace_id": ctx.workspace_id,
                        "workspace_name": ctx.workspace_name,
                        "events": [
                            {
                                "record": event.record,
                                "signature": event.signature,
                                "verified": event.verified,
                            }
                            for event in read_audit_events(ctx)
                        ],
                    }
                ]
            else:
                all_audits = []
                for item in mgr.list_workspaces():
                    try:
                        ctx = mgr.get_active_workspace(item["name"])
                    except CoWorkShieldError:
                        continue
                    all_audits.append(
                        {
                            "workspace_id": ctx.workspace_id,
                            "workspace_name": ctx.workspace_name,
                            "events": [
                                {
                                    "record": event.record,
                                    "signature": event.signature,
                                    "verified": event.verified,
                                }
                                for event in read_audit_events(ctx)
                            ],
                        }
                    )
                payload["audit_logs"] = all_audits

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        destination.chmod(stat.S_IRUSR | stat.S_IWUSR)

        log_event(
            "cli",
            py_logging.INFO,
            "logs_export_complete",
            "Logs exported",
            metadata={
                "output_path": str(destination),
                "workspace": workspace_name.strip(),
                "include_app": include_app,
                "include_audit": include_audit,
            },
        )

        console.print("[green]Logs exported.[/]")
        console.print(f"  Output: {destination}")
        console.print("  File mode: 600")

    except click.ClickException as e:
        _show_error(e)
        raise SystemExit(1)
    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@logs_group.command("delete")
@click.option(
    "-w",
    "--workspace",
    "workspace_name",
    default="",
    help="Optional workspace name whose signed audit log should be deleted.",
)
@click.option(
    "--all-audits",
    is_flag=True,
    help="Delete signed audit logs for all workspaces.",
)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def logs_delete(workspace_name, all_audits, yes):
    """Delete sanitized logs (non-audit and optional audit logs)."""
    try:
        workspace_name = workspace_name.strip()
        if workspace_name and all_audits:
            raise click.UsageError("Use either --workspace or --all-audits, not both.")

        if not yes:
            click.confirm(
                "Delete local log files? This removes support/debug history on this machine.",
                abort=True,
            )

        deleted_non_audit = delete_log_files()
        deleted_audit = 0

        mgr = WorkspaceManager()
        if workspace_name:
            ctx = mgr.get_active_workspace(workspace_name)
            if delete_audit_events(ctx):
                deleted_audit += 1
        elif all_audits:
            for item in mgr.list_workspaces():
                try:
                    ctx = mgr.get_active_workspace(item["name"])
                except CoWorkShieldError:
                    continue
                if delete_audit_events(ctx):
                    deleted_audit += 1

        log_event(
            "cli",
            py_logging.WARNING,
            "logs_deleted",
            "Logs deleted",
            metadata={
                "workspace": workspace_name,
                "all_audits": all_audits,
                "deleted_non_audit_files": deleted_non_audit,
                "deleted_audit_files": deleted_audit,
            },
        )

        console.print("[green]Log cleanup complete.[/]")
        console.print(f"  App log files deleted:   {deleted_non_audit}")
        console.print(f"  Audit log files deleted: {deleted_audit}")

    except click.Abort:
        console.print("Cancelled.")
    except click.ClickException as e:
        _show_error(e)
        raise SystemExit(1)
    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "-o", "--output", type=click.Path(), default=None,
    help="Output file path (default: FILE.anonymized.EXT)",
)
@click.option(
    "-w", "--workspace", type=str, default="default",
    help="Workspace name for identity sharing across files",
)
@click.option(
    "--ttl", type=int, default=168,
    help="Vault TTL in hours (default: 168 = 7 days)",
)
@click.option(
    "--score-threshold", type=float, default=0.7,
    help="Minimum Presidio confidence score (0.0-1.0)",
)
@click.option(
    "--language",
    type=click.Choice(LANGUAGE_CHOICES, case_sensitive=False),
    default="auto",
    help="Detection language: auto, en, or he.",
)
@click.option(
    "--hebrew-backend",
    type=click.Choice(HEBREW_BACKEND_CHOICES, case_sensitive=False),
    default="auto",
    hidden=True,
    help="Hebrew NLP backend: auto, spacy, stanza, or transformers.",
)
@click.option(
    "--hebrew-stanza-model",
    type=str,
    default="he",
    show_default=True,
    hidden=True,
    help="Stanza model id for Hebrew backend.",
)
@click.option(
    "--hebrew-transformer-model",
    type=str,
    default="CordwainerSmith/GolemPII-v1",
    show_default=True,
    hidden=True,
    help="Transformers model id for Hebrew backend.",
)
@click.option(
    "--allow-lossy-xlsx",
    is_flag=True,
    help="Allow XLSX processing even when chart/image loss risk is detected.",
)
@click.option(
    "--pdf-output-format",
    type=click.Choice(["md", "docx"], case_sensitive=False),
    default="md",
    show_default=True,
    help="Output format when input file is PDF (PDF is input-only).",
)
@click.option(
    "--columns",
    type=str,
    default="",
    help='Comma-separated spreadsheet columns (letters or names). Example: A,C,F or "Client Name,Deal ID".',
)
@click.option(
    "--detect-pii/--no-detect-pii",
    default=None,
    help=(
        "Run Presidio detection in addition to selected columns. "
        "Default: true when --columns is empty; false when --columns is provided."
    ),
)
@click.option(
    "--force-reanonymize",
    is_flag=True,
    help="Override deterministic/model lock checks (requires --reason).",
)
@click.option(
    "--reason",
    type=str,
    default="",
    help="Audit reason for --force-reanonymize.",
)
def anonymize(
    file,
    output,
    workspace,
    ttl,
    score_threshold,
    language,
    hebrew_backend,
    hebrew_stanza_model,
    hebrew_transformer_model,
    allow_lossy_xlsx,
    pdf_output_format,
    columns,
    detect_pii,
    force_reanonymize,
    reason,
):
    """Anonymize PII in a document.

    Detects personally identifiable information, replaces it with
    deterministic tokens, and stores the mapping in an encrypted vault.

    \b
    Examples:
        cowork-shield anonymize report.xlsx
        cowork-shield anonymize data.csv -w client-acme
        cowork-shield anonymize contract.docx -o contract.safe.docx
        cowork-shield anonymize notes.txt --language he
        cowork-shield anonymize intake.pdf --pdf-output-format md
        cowork-shield anonymize deals.xlsx --columns "Deal ID,Client Name"
        cowork-shield anonymize deals.csv --columns A,C --detect-pii
    """
    try:
        log_event(
            "cli",
            py_logging.INFO,
            "anonymize_command_start",
            "Anonymize command started",
            metadata={
                "file_path": str(file),
                "workspace": workspace,
                "language": language,
                "columns_specified": bool(columns.strip()),
                "force_reanonymize": force_reanonymize,
            },
        )
        if force_reanonymize and not reason.strip():
            raise click.UsageError(
                "--force-reanonymize requires --reason for audit logging."
            )

        mgr = WorkspaceManager()
        ctx, _created = _get_or_create_workspace_with_warning(mgr, workspace, ttl_hours=ttl)

        input_path = Path(file)
        output_path = Path(output) if output else None
        selected_columns = parse_columns_option(columns)

        if input_path.suffix.lower() == ".pdf":
            console.print(
                "[bold yellow]PDF input warning:[/] "
                "This will output [bold].md[/] or [bold].docx[/], not a reconstructed PDF."
            )

        pipeline = AnonymizePipeline(
            ctx,
            score_threshold=score_threshold,
            language=language.lower(),
            hebrew_backend=hebrew_backend.lower(),
            hebrew_stanza_model=hebrew_stanza_model.strip(),
            hebrew_transformer_model=hebrew_transformer_model.strip(),
            force_reanonymize=force_reanonymize,
            override_reason=reason,
            override_user=getpass.getuser(),
            allow_lossy_xlsx=allow_lossy_xlsx,
            pdf_output_format=pdf_output_format.lower(),
            selected_columns=selected_columns,
            detect_pii=detect_pii,
        )

        if input_path.suffix.lower() in {".csv", ".xlsx"} and not selected_columns:
            try:
                columns_info = inspect_columns(input_path)
                if columns_info:
                    console.print("[dim]Available columns:[/]")
                    console.print(
                        "[dim]"
                        + ", ".join(f"{col.letter}:{col.name}" for col in columns_info)
                        + "[/]"
                    )
            except CoWorkShieldError:
                pass

        result = pipeline.run(input_path, output_path)

        console.print()
        console.print(f"[bold green]Anonymized[/] {result.input_path.name}")
        console.print(f"  Output:    {result.output_path}")
        console.print(f"  Workspace: {result.workspace_name}")
        console.print(f"  Entities:  {result.entities_found} detected")
        console.print(f"  Tokens:    {result.tokens_applied} applied")
        if selected_columns:
            effective_detect = detect_pii if detect_pii is not None else False
            mode = "column + pii" if effective_detect else "column-only"
            console.print(f"  Columns:   {', '.join(selected_columns)} ({mode})")
        if force_reanonymize:
            console.print(f"  Override:  [yellow]ON[/] ({reason.strip()})")
        if result.backup_path:
            console.print(f"  Backup:    {result.backup_path}")
        if input_path.suffix.lower() == ".pdf":
            console.print(
                "  Note:      [yellow]PDF is input-only[/]. Output is extracted "
                "Markdown/DOCX and original PDF layout is not reconstructed."
            )
        console.print()
        log_event(
            "cli",
            py_logging.INFO,
            "anonymize_command_complete",
            "Anonymize command complete",
            workspace_id=ctx.workspace_id,
            metadata={
                "file_path": str(input_path),
                "file_ext": input_path.suffix.lower(),
                "entities_found": result.entities_found,
                "tokens_applied": result.tokens_applied,
            },
        )

    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@main.command("inspect-columns")
@click.argument("file", type=click.Path(exists=True))
def inspect_columns_cmd(file):
    """Inspect selectable columns for CSV/XLSX files."""
    try:
        input_path = Path(file)
        columns = inspect_columns(input_path)
        if not columns:
            console.print("[yellow]No columns found.[/]")
            return

        table = Table(title=f"Columns: {input_path.name}")
        table.add_column("Index", style="cyan")
        table.add_column("Letter", style="green")
        table.add_column("Name", style="white")
        table.add_column("Type", style="magenta")
        table.add_column("Sample Values", style="dim")

        for column in columns:
            sample_text = " | ".join(column.sample_values) if column.sample_values else "-"
            table.add_row(
                str(column.index),
                column.letter,
                column.name,
                column.data_type,
                sample_text,
            )

        console.print(table)
        console.print(
            '[dim]Use --columns with letters or names, e.g. --columns A,C or --columns "Client Name,Deal ID".[/]'
        )
    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "-o", "--output", type=click.Path(), default=None,
    help="Output file path (default: FILE.restored.EXT)",
)
@click.option(
    "-w", "--workspace", type=str, default="default",
    help="Workspace to restore from",
)
def restore(file, output, workspace):
    """Restore an anonymized document to its original form.

    Reads the encrypted vault, verifies all HMAC tags, replaces
    tokens with original values, and verifies completeness.

    If any verification fails, restoration aborts entirely.

    \b
    Examples:
        cowork-shield restore report.anonymized.xlsx
        cowork-shield restore data.csv -w client-acme
        cowork-shield restore intake.anonymized.md -w client-acme
    """
    try:
        log_event(
            "cli",
            py_logging.INFO,
            "restore_command_start",
            "Restore command started",
            metadata={"file_path": str(file), "workspace": workspace},
        )
        mgr = WorkspaceManager()
        ctx = mgr.get_active_workspace(workspace)

        input_path = Path(file)
        output_path = Path(output) if output else None

        pipeline = RestorePipeline(ctx)
        result = pipeline.run(input_path, output_path)

        console.print()
        console.print(f"[bold green]Restored[/] {result.input_path.name}")
        console.print(f"  Output:       {result.output_path}")
        console.print(f"  Workspace:    {result.workspace_name}")
        console.print(f"  Tokens:       {result.tokens_restored} restored")
        console.print("  Verification: [green]PASSED[/]")
        console.print()
        log_event(
            "cli",
            py_logging.INFO,
            "restore_command_complete",
            "Restore command complete",
            workspace_id=ctx.workspace_id,
            metadata={
                "file_path": str(input_path),
                "file_ext": input_path.suffix.lower(),
                "tokens_restored": result.tokens_restored,
            },
        )

    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@main.command("shield-clipboard")
@click.option(
    "-w", "--workspace", type=str, default="default",
    help="Workspace name for identity sharing across operations",
)
@click.option(
    "--score-threshold", type=float, default=0.7,
    help="Minimum Presidio confidence score (0.0-1.0)",
)
@click.option(
    "--language",
    type=click.Choice(LANGUAGE_CHOICES, case_sensitive=False),
    default="auto",
    help="Detection language: auto, en, or he.",
)
@click.option(
    "--hebrew-backend",
    type=click.Choice(HEBREW_BACKEND_CHOICES, case_sensitive=False),
    default="auto",
    hidden=True,
    help="Hebrew NLP backend: auto, spacy, stanza, or transformers.",
)
@click.option(
    "--hebrew-stanza-model",
    type=str,
    default="he",
    show_default=True,
    hidden=True,
    help="Stanza model id for Hebrew backend.",
)
@click.option(
    "--hebrew-transformer-model",
    type=str,
    default="CordwainerSmith/GolemPII-v1",
    show_default=True,
    hidden=True,
    help="Transformers model id for Hebrew backend.",
)
@click.option(
    "--force-reanonymize",
    is_flag=True,
    help="Override deterministic/model lock checks (requires --reason).",
)
@click.option(
    "--reason",
    type=str,
    default="",
    help="Audit reason for --force-reanonymize.",
)
def shield_clipboard_cmd(
    workspace,
    score_threshold,
    language,
    hebrew_backend,
    hebrew_stanza_model,
    hebrew_transformer_model,
    force_reanonymize,
    reason,
):
    """Anonymize current clipboard contents in place.

    Example:
        cowork-shield shield-clipboard -w client-a --language he
    """
    try:
        log_event(
            "cli",
            py_logging.INFO,
            "clipboard_anonymize_start",
            "Clipboard anonymize started",
            metadata={"workspace": workspace, "language": language},
        )
        if force_reanonymize and not reason.strip():
            raise click.UsageError(
                "--force-reanonymize requires --reason for audit logging."
            )

        mgr = WorkspaceManager()
        ctx, _created = _get_or_create_workspace_with_warning(mgr, workspace)

        result = shield_clipboard(
            ctx,
            score_threshold=score_threshold,
            language=language.lower(),
            hebrew_backend=hebrew_backend.lower(),
            hebrew_stanza_model=hebrew_stanza_model.strip(),
            hebrew_transformer_model=hebrew_transformer_model.strip(),
            force_reanonymize=force_reanonymize,
            override_reason=reason,
            override_user=getpass.getuser(),
        )

        console.print()
        console.print("[bold green]Clipboard anonymized[/]")
        console.print(f"  Workspace: {workspace}")
        console.print(f"  Entities:  {result.entities_found} detected")
        console.print(f"  Tokens:    {result.tokens_applied} applied")
        if force_reanonymize:
            console.print(f"  Override:  [yellow]ON[/] ({reason.strip()})")
        console.print()
        log_event(
            "cli",
            py_logging.INFO,
            "clipboard_anonymize_complete",
            "Clipboard anonymize complete",
            workspace_id=ctx.workspace_id,
            metadata={
                "entities_found": result.entities_found,
                "tokens_applied": result.tokens_applied,
            },
        )

    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@main.command("restore-clipboard")
@click.option(
    "-w", "--workspace", type=str, default="default",
    help="Workspace to restore from",
)
def restore_clipboard_cmd(workspace):
    """Restore tokenized clipboard contents in place."""
    try:
        log_event(
            "cli",
            py_logging.INFO,
            "clipboard_restore_start",
            "Clipboard restore started",
            metadata={"workspace": workspace},
        )
        mgr = WorkspaceManager()
        ctx = mgr.get_active_workspace(workspace)

        result = restore_clipboard(ctx)

        console.print()
        console.print("[bold green]Clipboard restored[/]")
        console.print(f"  Workspace:    {workspace}")
        console.print(f"  Tokens:       {result.tokens_restored} restored")
        console.print("  Verification: [green]PASSED[/]")
        console.print()
        log_event(
            "cli",
            py_logging.INFO,
            "clipboard_restore_complete",
            "Clipboard restore complete",
            workspace_id=ctx.workspace_id,
            metadata={"tokens_restored": result.tokens_restored},
        )

    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@main.command("ipc-server")
@click.option(
    "--socket-path",
    type=click.Path(),
    default=str(Path.home() / ".cowork-shield" / "ipc" / "engine.sock"),
    show_default=True,
    help="UNIX domain socket path for wrapper IPC.",
)
@click.pass_context
def ipc_server_cmd(ctx, socket_path):
    """Run the AF_UNIX IPC daemon used by the Swift wrapper."""
    configure_logging(
        component="engine",
        verbose=bool(ctx.obj.get("verbose")),
        no_logging=bool(ctx.obj.get("no_logging")),
        encrypt_logs=bool(ctx.obj.get("encrypt_logs")),
    )
    server = IPCServer(socket_path)
    try:
        console.print(f"[cyan]Starting IPC server:[/] {Path(socket_path).expanduser()}")
        log_event(
            "engine",
            py_logging.INFO,
            "ipc_server_start",
            "IPC socket server started",
            metadata={"socket_path": str(Path(socket_path).expanduser())},
        )
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]IPC server interrupted.[/]")
    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)
    finally:
        server.stop()


@main.command("ipc-stdio")
@click.pass_context
def ipc_stdio_cmd(ctx):
    """Run the subprocess stdin/stdout IPC bridge (hybrid Mode A)."""
    try:
        configure_logging(
            component="engine",
            verbose=bool(ctx.obj.get("verbose")),
            no_logging=bool(ctx.obj.get("no_logging")),
            encrypt_logs=bool(ctx.obj.get("encrypt_logs")),
        )
        stdio_server_main([])
    except KeyboardInterrupt:
        console.print("\n[yellow]IPC stdio bridge interrupted.[/]")
    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@main.group("workspace")
def workspace_group():
    """Manage anonymization workspaces."""
    pass


@workspace_group.command("list")
def workspace_list():
    """List all workspaces with status."""
    try:
        mgr = WorkspaceManager()
        workspaces = mgr.list_workspaces()

        if not workspaces:
            console.print("No workspaces found.")
            return

        table = Table(title="Workspaces")
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Mappings", justify="right")
        table.add_column("Files", justify="right")

        for ws in workspaces:
            status_style = "green" if ws["status"] == "active" else "red"
            table.add_row(
                ws["name"],
                f"[{status_style}]{ws['status']}[/{status_style}]",
                str(ws["mappings"]),
                str(ws["files"]),
            )

        console.print(table)

    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@workspace_group.command("show")
@click.argument("name")
@click.option("--show-mappings", is_flag=True, help="Display all token mappings")
@click.option("--audit", "show_audit", is_flag=True, help="Display signed workspace audit events")
def workspace_show(name, show_mappings, show_audit):
    """Show details of a workspace."""
    try:
        mgr = WorkspaceManager()
        ctx = mgr.get_active_workspace(name)

        console.print(f"\n[bold]Workspace:[/] {ctx.workspace_name}")
        console.print(f"  ID:       {ctx.workspace_id}")
        console.print(f"  Created:  {ctx.vault_data.created_at}")
        console.print(f"  Updated:  {ctx.vault_data.updated_at}")
        console.print(f"  TTL:      {ctx.vault_data.ttl_hours}h")
        console.print(f"  Mappings: {len(ctx.vault_data.mappings)}")
        console.print(f"  Files:    {len(ctx.vault_data.file_records)}")

        if ctx.vault_data.file_records:
            console.print("\n  [bold]Files processed:[/]")
            for fr in ctx.vault_data.file_records:
                console.print(f"    - {fr.file_path} ({fr.format}, {fr.entities_found} entities)")

        if show_mappings and ctx.vault_data.mappings:
            table = Table(title="Token Mappings")
            table.add_column("Token", style="cyan")
            table.add_column("Type")
            table.add_column("Original Value", style="yellow")
            table.add_column("Source Files")

            for mapping in ctx.vault_data.mappings.values():
                table.add_row(
                    mapping.token.token_text,
                    mapping.entity_type.value,
                    mapping.original_value,
                    ", ".join(mapping.source_files),
                )

            console.print()
            console.print(table)

        if show_audit:
            events = read_audit_events(ctx)
            if not events:
                console.print("\n[yellow]No audit events found.[/]")
            else:
                audit_table = Table(title="Audit Events")
                audit_table.add_column("Timestamp", style="cyan")
                audit_table.add_column("Event", style="white")
                audit_table.add_column("Verified", style="green")
                audit_table.add_column("Fields", style="dim")
                for row in events[-50:]:
                    record = row.record
                    fields = record.get("fields", {})
                    fields_text = ", ".join(
                        f"{k}={v}" for k, v in fields.items()
                    )[:200]
                    verified_text = "yes" if row.verified else "no"
                    audit_table.add_row(
                        str(record.get("timestamp", "")),
                        str(record.get("event", "")),
                        verified_text,
                        fields_text,
                    )
                console.print()
                console.print(audit_table)

        console.print()

    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@workspace_group.command("verify-security")
@click.option(
    "-w",
    "--workspace",
    "workspace_name",
    default="",
    help="Optional workspace name to scope vault-permission checks.",
)
def workspace_verify_security(workspace_name):
    """Verify keychain and vault file permission hardening."""
    try:
        mgr = WorkspaceManager()
        names: list[str]
        if workspace_name.strip():
            names = [workspace_name.strip()]
            mgr.get_workspace_metadata(names[0])
        else:
            names = [item["name"] for item in mgr.list_workspaces()]

        table = Table(title="Security Verification")
        table.add_column("Check", style="cyan")
        table.add_column("Target")
        table.add_column("Result")
        table.add_column("Detail", style="dim")

        failures = 0
        for name in names:
            metadata = mgr.get_workspace_metadata(name)
            vault_path = Path(metadata["vault_path"])
            if not vault_path.exists():
                failures += 1
                table.add_row(
                    "Vault File Permissions",
                    name,
                    "[red]FAIL[/]",
                    f"Missing vault file: {vault_path}",
                )
                continue

            mode_value = vault_path.stat().st_mode & 0o777
            mode_text = stat.filemode(vault_path.stat().st_mode)
            if mode_value != 0o600:
                failures += 1
                table.add_row(
                    "Vault File Permissions",
                    name,
                    "[red]FAIL[/]",
                    f"{vault_path} mode {mode_text} (expected -rw-------)",
                )
            else:
                table.add_row(
                    "Vault File Permissions",
                    name,
                    "[green]PASS[/]",
                    f"{vault_path} mode {mode_text}",
                )

        keychain_ok, keychain_detail = verify_keychain_permissions()
        if not keychain_ok:
            failures += 1
        table.add_row(
            "Keychain Service Check",
            "cowork-shield",
            "[green]PASS[/]" if keychain_ok else "[red]FAIL[/]",
            keychain_detail,
        )

        console.print(table)
        log_event(
            "cli",
            py_logging.INFO,
            "workspace_verify_security",
            "Workspace security verification complete",
            metadata={
                "workspace_scope": workspace_name.strip(),
                "failures": failures,
                "keychain_ok": keychain_ok,
                "workspaces_checked": len(names),
            },
        )

        if failures:
            raise SystemExit(1)

    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@workspace_group.command("export-key")
@click.option(
    "-w", "--workspace", "workspace_name", required=True,
    help="Workspace name to export the recovery key for.",
)
@click.option(
    "-o", "--output", "output_path", type=click.Path(), required=True,
    help="Destination file path for encrypted recovery key payload.",
)
@click.option(
    "--passphrase", default=None,
    help="Passphrase used to encrypt export payload (prompted if omitted).",
)
@click.option(
    "--force", is_flag=True,
    help="Overwrite output file if it already exists.",
)
def workspace_export_key(workspace_name, output_path, passphrase, force):
    """Export workspace master key as an encrypted recovery payload."""
    try:
        mgr = WorkspaceManager()
        ctx = mgr.get_active_workspace(workspace_name)
        workspace_id = ctx.workspace_id
        master_key = ctx.master_key

        destination = Path(output_path).expanduser()
        if destination.exists() and not force:
            raise click.ClickException(
                f"Output already exists: {destination}. Use --force to overwrite."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)

        resolved_passphrase = _resolve_passphrase(passphrase, confirm=True)
        payload = export_encrypted_master_key(
            workspace_id=workspace_id,
            master_key=master_key,
            passphrase=resolved_passphrase,
        )
        destination.write_bytes(payload)
        destination.chmod(stat.S_IRUSR | stat.S_IWUSR)

        append_audit_event(
            ctx,
            event="key_exported",
            fields={
                "user": getpass.getuser(),
                "export_path": str(destination.resolve()),
            },
        )
        log_event(
            "cli",
            py_logging.WARNING,
            "workspace_key_exported",
            "Workspace recovery key exported",
            workspace_id=ctx.workspace_id,
            metadata={"output_path": str(destination.resolve())},
        )

        console.print("[green]Recovery key exported.[/]")
        console.print(f"  Workspace: {workspace_name}")
        console.print(f"  Output:    {destination}")
        console.print("  File mode: 600")

    except click.ClickException as e:
        _show_error(e)
        raise SystemExit(1)
    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@workspace_group.command("import-key")
@click.option(
    "-w", "--workspace", "workspace_name", required=True,
    help="Workspace name to restore the recovery key to.",
)
@click.option(
    "-i", "--input", "input_path", type=click.Path(exists=True), required=True,
    help="Encrypted recovery key payload file.",
)
@click.option(
    "--passphrase", default=None,
    help="Passphrase used to decrypt export payload (prompted if omitted).",
)
@click.option(
    "--force", is_flag=True,
    help="Replace existing Keychain entry (admin-only use).",
)
def workspace_import_key(workspace_name, input_path, passphrase, force):
    """Import an encrypted recovery payload into macOS Keychain."""
    try:
        mgr = WorkspaceManager()
        metadata = mgr.get_workspace_metadata(workspace_name)
        workspace_id = metadata["workspace_id"]

        existing_key = get_master_key(workspace_id)
        if existing_key is not None and not force:
            raise click.ClickException(
                "Keychain entry already exists for this workspace. "
                "Use --force to replace it."
            )

        blob = Path(input_path).expanduser().read_bytes()
        resolved_passphrase = _resolve_passphrase(passphrase, confirm=False)
        _, master_key = import_encrypted_master_key(
            blob=blob,
            passphrase=resolved_passphrase,
            expected_workspace_id=workspace_id,
        )
        store_master_key(workspace_id, master_key)

        console.print("[green]Recovery key imported.[/]")
        console.print(f"  Workspace: {workspace_name}")
        if force:
            console.print("  Mode:      forced replace")

        ctx = mgr.get_active_workspace(workspace_name)
        append_audit_event(
            ctx,
            event="key_imported",
            fields={
                "user": getpass.getuser(),
                "source_path": str(Path(input_path).expanduser().resolve()),
                "force": bool(force),
            },
        )
        log_event(
            "cli",
            py_logging.WARNING,
            "workspace_key_imported",
            "Workspace recovery key imported",
            workspace_id=ctx.workspace_id,
            metadata={
                "input_path": str(Path(input_path).expanduser().resolve()),
                "force": bool(force),
            },
        )

    except click.ClickException as e:
        _show_error(e)
        raise SystemExit(1)
    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@workspace_group.command("delete")
@click.argument("name")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def workspace_delete(name, force):
    """Delete a workspace and its vault."""
    try:
        if not force:
            click.confirm(
                f"Delete workspace '{name}'? This cannot be undone.", abort=True
            )

        mgr = WorkspaceManager()
        mgr.delete_workspace(name)
        console.print(f"[green]Deleted workspace:[/] {name}")

    except click.Abort:
        console.print("Cancelled.")
    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)


@workspace_group.command("cleanup")
def workspace_cleanup():
    """Remove all expired workspaces."""
    try:
        mgr = WorkspaceManager()
        count = mgr.cleanup_expired()
        console.print(f"[green]Cleaned up {count} expired workspace(s).[/]")

    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)
