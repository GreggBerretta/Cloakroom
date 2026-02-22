"""Gradio web UI for CoWork Shield."""

from __future__ import annotations

from pathlib import Path

import gradio as gr

from cowork_shield.exceptions import CoWorkShieldError
from cowork_shield.pipeline import (
    anonymize_file,
    get_file_columns,
    get_workspaces,
    restore_file,
    sanitize_ui_error,
)


def _workspace_choices() -> list[str]:
    return get_workspaces()


def _normalize_workspace(workspace: str | None) -> str:
    value = (workspace or "").strip()
    return value or "default"


def _refresh_workspace_dropdown():
    choices = _workspace_choices()
    value = "default" if "default" in choices else (choices[0] if choices else "default")
    return gr.Dropdown(choices=choices, value=value)


def _refresh_column_dropdown(uploaded_file):
    if uploaded_file is None:
        return gr.Dropdown(choices=[], value=None)

    input_path = Path(uploaded_file.name)
    try:
        columns = get_file_columns(input_path)
    except (CoWorkShieldError, OSError):
        return gr.Dropdown(choices=[], value=None)

    choices = [(column["label"], column["name"]) for column in columns]
    return gr.Dropdown(choices=choices, value=None)


def shield(
    uploaded_file,
    workspace,
    language,
    pdf_output_format,
    selected_columns,
    detect_pii,
    allow_lossy_xlsx,
    force_reanonymize,
    override_reason,
    confirm_risky_operation,
):
    if uploaded_file is None:
        return None, "<p><strong>No file uploaded.</strong></p>", "No file uploaded."

    reason = (override_reason or "").strip()
    if force_reanonymize and not reason:
        return (
            None,
            "<p><strong>Missing override reason.</strong></p>",
            "Reason is required when force re-anonymize is enabled.",
        )

    if (allow_lossy_xlsx or force_reanonymize) and not confirm_risky_operation:
        return (
            None,
            "<p><strong>Confirmation required.</strong></p>",
            "Enable confirmation to proceed with risky anonymize overrides.",
        )

    workspace_name = _normalize_workspace(workspace)
    language_value = (language or "auto").strip().lower() or "auto"
    input_path = Path(uploaded_file.name)
    selected = [str(item).strip() for item in (selected_columns or []) if str(item).strip()]
    effective_detect_pii = bool(detect_pii) if selected else True

    try:
        result = anonymize_file(
            input_path,
            workspace_name,
            language=language_value,
            pdf_output_format=(pdf_output_format or "md").strip().lower(),
            columns=selected,
            detect_pii=effective_detect_pii,
            allow_lossy_xlsx=bool(allow_lossy_xlsx),
            force_reanonymize=bool(force_reanonymize),
            reason=reason,
        )
        return result.path, result.entity_table_html, result.summary
    except (CoWorkShieldError, OSError) as exc:
        code, message = sanitize_ui_error(exc)
        return None, "<p><strong>Failed to anonymize.</strong></p>", f"{code}: {message}"


def restore(uploaded_file, workspace):
    if uploaded_file is None:
        return None, "No file uploaded."

    workspace_name = _normalize_workspace(workspace)
    input_path = Path(uploaded_file.name)

    try:
        result = restore_file(input_path, workspace_name)
        return result.path, result.summary
    except (CoWorkShieldError, OSError) as exc:
        code, message = sanitize_ui_error(exc)
        return None, f"{code}: {message}"


def create_demo() -> gr.Blocks:
    choices = _workspace_choices()
    default_workspace = "default" if "default" in choices else (choices[0] if choices else "default")

    with gr.Blocks(title="CoWork Shield (HANDOFF B)") as demo:
        gr.Markdown(
            """
            # CoWork Shield Web UI
            Upload a file, choose a workspace, then anonymize or restore.
            PDF files are input-only and are converted to Markdown/DOCX output.
            """
        )
        gr.Markdown(
            """
            **Security Warning:** This UI is for local use only.
            Keep binding on `127.0.0.1`; do not expose this service to external networks.
            """
        )

        with gr.Tab("Shield"):
            shield_file = gr.File(label="Input File")
            shield_workspace = gr.Dropdown(
                choices=choices,
                value=default_workspace,
                label="Workspace",
                allow_custom_value=True,
            )
            shield_language = gr.Dropdown(
                choices=["auto", "en", "he"],
                value="auto",
                label="Detection Language",
            )
            column_selector = gr.Dropdown(
                choices=[],
                value=None,
                multiselect=True,
                label="Columns to anonymize (CSV/XLSX only)",
                info="Select columns by header name for column-selective anonymization.",
            )
            detect_pii = gr.Checkbox(
                label="Run PII detection on non-selected columns (--detect-pii)",
                value=False,
            )
            pdf_output_format = gr.Dropdown(
                choices=["md", "docx"],
                value="md",
                label="PDF output format (input-only PDF pipeline)",
            )
            allow_lossy_xlsx = gr.Checkbox(
                label="Allow lossy XLSX processing (--allow-lossy-xlsx)",
                value=False,
            )
            force_reanonymize = gr.Checkbox(
                label="Force re-anonymize (--force-reanonymize)",
                value=False,
            )
            override_reason = gr.Textbox(
                label="Override reason (required when force re-anonymize is enabled)",
                placeholder="Required for audited force override",
            )
            confirm_risky_operation = gr.Checkbox(
                label="I confirm I want to proceed with risky overrides",
                value=False,
            )
            with gr.Row():
                shield_btn = gr.Button("Anonymize", variant="primary")
                shield_refresh = gr.Button("Refresh Workspaces")
            shield_output_file = gr.File(label="Anonymized Output")
            shield_entity_table = gr.HTML(label="Detected Entities")
            shield_status = gr.Textbox(label="Status", interactive=False)

            shield_file.change(
                fn=_refresh_column_dropdown,
                inputs=[shield_file],
                outputs=[column_selector],
            )
            shield_btn.click(
                fn=shield,
                inputs=[
                    shield_file,
                    shield_workspace,
                    shield_language,
                    pdf_output_format,
                    column_selector,
                    detect_pii,
                    allow_lossy_xlsx,
                    force_reanonymize,
                    override_reason,
                    confirm_risky_operation,
                ],
                outputs=[shield_output_file, shield_entity_table, shield_status],
            )
            shield_refresh.click(
                fn=_refresh_workspace_dropdown,
                inputs=[],
                outputs=[shield_workspace],
            )

        with gr.Tab("Restore"):
            restore_file_input = gr.File(label="Anonymized File")
            restore_workspace = gr.Dropdown(
                choices=choices,
                value=default_workspace,
                label="Workspace",
                allow_custom_value=True,
            )
            with gr.Row():
                restore_btn = gr.Button("Restore", variant="primary")
                restore_refresh = gr.Button("Refresh Workspaces")
            restore_output_file = gr.File(label="Restored Output")
            restore_status = gr.Textbox(label="Status", interactive=False)

            restore_btn.click(
                fn=restore,
                inputs=[restore_file_input, restore_workspace],
                outputs=[restore_output_file, restore_status],
            )
            restore_refresh.click(
                fn=_refresh_workspace_dropdown,
                inputs=[],
                outputs=[restore_workspace],
            )

    return demo


def launch() -> None:
    create_demo().launch(server_name="127.0.0.1")


if __name__ == "__main__":
    launch()
