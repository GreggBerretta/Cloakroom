"""CLI entry point for CoWork Shield."""

from __future__ import annotations

import getpass
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
from cowork_shield.exceptions import CoWorkShieldError
from cowork_shield.pipeline.anonymize import AnonymizePipeline
from cowork_shield.pipeline.columns import inspect_columns
from cowork_shield.pipeline.restore import RestorePipeline
from cowork_shield.vault.keychain import get_master_key, store_master_key
from cowork_shield.vault.recovery import (
    export_encrypted_master_key,
    import_encrypted_master_key,
)
from cowork_shield.workspace.manager import WorkspaceManager

console = Console()


def _show_error(exc: Exception) -> None:
    code = exc.__class__.__name__
    console.print(f"[bold red]Error [{code}]:[/] {exc}")


def _resolve_passphrase(passphrase: str | None, *, confirm: bool) -> str:
    if passphrase:
        return passphrase
    return click.prompt(
        "Passphrase",
        hide_input=True,
        confirmation_prompt=confirm,
    )


@click.group()
@click.version_option(package_name="cowork-shield")
def main():
    """CoWork Shield -- Reversible document anonymization for safe LLM usage."""
    pass


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
    help="Hebrew NLP backend: auto, spacy, stanza, or transformers.",
)
@click.option(
    "--hebrew-stanza-model",
    type=str,
    default="he",
    show_default=True,
    help="Stanza model id for Hebrew backend.",
)
@click.option(
    "--hebrew-transformer-model",
    type=str,
    default="CordwainerSmith/GolemPII-v1",
    show_default=True,
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
        if force_reanonymize and not reason.strip():
            raise click.UsageError(
                "--force-reanonymize requires --reason for audit logging."
            )

        mgr = WorkspaceManager()
        ctx = mgr.get_or_create_workspace(workspace, ttl_hours=ttl)

        input_path = Path(file)
        output_path = Path(output) if output else None
        selected_columns = parse_columns_option(columns)

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
    help="Hebrew NLP backend: auto, spacy, stanza, or transformers.",
)
@click.option(
    "--hebrew-stanza-model",
    type=str,
    default="he",
    show_default=True,
    help="Stanza model id for Hebrew backend.",
)
@click.option(
    "--hebrew-transformer-model",
    type=str,
    default="CordwainerSmith/GolemPII-v1",
    show_default=True,
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
        if force_reanonymize and not reason.strip():
            raise click.UsageError(
                "--force-reanonymize requires --reason for audit logging."
            )

        mgr = WorkspaceManager()
        ctx = mgr.get_or_create_workspace(workspace)

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
        mgr = WorkspaceManager()
        ctx = mgr.get_active_workspace(workspace)

        result = restore_clipboard(ctx)

        console.print()
        console.print("[bold green]Clipboard restored[/]")
        console.print(f"  Workspace:    {workspace}")
        console.print(f"  Tokens:       {result.tokens_restored} restored")
        console.print("  Verification: [green]PASSED[/]")
        console.print()

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
def ipc_server_cmd(socket_path):
    """Run the AF_UNIX IPC daemon used by the Swift wrapper."""
    server = IPCServer(socket_path)
    try:
        console.print(f"[cyan]Starting IPC server:[/] {Path(socket_path).expanduser()}")
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]IPC server interrupted.[/]")
    except CoWorkShieldError as e:
        _show_error(e)
        raise SystemExit(1)
    finally:
        server.stop()


@main.command("ipc-stdio")
def ipc_stdio_cmd():
    """Run the subprocess stdin/stdout IPC bridge (hybrid Mode A)."""
    try:
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
def workspace_show(name, show_mappings):
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

        console.print()

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
        metadata = mgr.get_workspace_metadata(workspace_name)
        workspace_id = metadata["workspace_id"]

        master_key = get_master_key(workspace_id)
        if master_key is None:
            raise click.ClickException(
                "No key found in Keychain for this workspace. "
                "Recovery export is not possible."
            )

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
