"""Gradio web UI for CoWork Shield."""

from __future__ import annotations

from pathlib import Path

import gradio as gr

from cowork_shield.exceptions import CoWorkShieldError
from cowork_shield.pipeline import anonymize_file, get_workspaces, restore_file


def _workspace_choices() -> list[str]:
    return get_workspaces()


def _normalize_workspace(workspace: str | None) -> str:
    value = (workspace or "").strip()
    return value or "default"


def _refresh_workspace_dropdown():
    choices = _workspace_choices()
    value = "default" if "default" in choices else (choices[0] if choices else "default")
    return gr.Dropdown(choices=choices, value=value)


def shield(uploaded_file, workspace):
    if uploaded_file is None:
        return None, "<p><strong>No file uploaded.</strong></p>", "No file uploaded."

    workspace_name = _normalize_workspace(workspace)
    input_path = Path(uploaded_file.name)

    try:
        result = anonymize_file(input_path, workspace_name)
        return result.path, result.entity_table_html, result.summary
    except (CoWorkShieldError, OSError) as exc:
        return None, "<p><strong>Failed to anonymize.</strong></p>", (
            f"{exc.__class__.__name__}: {exc}"
        )


def restore(uploaded_file, workspace):
    if uploaded_file is None:
        return None, "No file uploaded."

    workspace_name = _normalize_workspace(workspace)
    input_path = Path(uploaded_file.name)

    try:
        result = restore_file(input_path, workspace_name)
        return result.path, result.summary
    except (CoWorkShieldError, OSError) as exc:
        return None, f"{exc.__class__.__name__}: {exc}"


def create_demo() -> gr.Blocks:
    choices = _workspace_choices()
    default_workspace = "default" if "default" in choices else (choices[0] if choices else "default")

    with gr.Blocks(title="CoWork Shield (HANDOFF B)") as demo:
        gr.Markdown(
            """
            # CoWork Shield Web UI
            Upload a file, choose a workspace, then anonymize or restore.
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
            with gr.Row():
                shield_btn = gr.Button("Anonymize", variant="primary")
                shield_refresh = gr.Button("Refresh Workspaces")
            shield_output_file = gr.File(label="Anonymized Output")
            shield_entity_table = gr.HTML(label="Detected Entities")
            shield_status = gr.Textbox(label="Status", interactive=False)

            shield_btn.click(
                fn=shield,
                inputs=[shield_file, shield_workspace],
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
    create_demo().launch()


if __name__ == "__main__":
    launch()

