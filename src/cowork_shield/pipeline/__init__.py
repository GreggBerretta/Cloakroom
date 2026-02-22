"""Public pipeline API exports."""

from cowork_shield.pipeline.ui_api import (
    UIOperationResult,
    anonymize_file,
    get_workspaces,
    preview_entities,
    render_entity_table,
    sanitize_ui_error,
    restore_file,
)

__all__ = [
    "UIOperationResult",
    "anonymize_file",
    "restore_file",
    "preview_entities",
    "render_entity_table",
    "get_workspaces",
    "sanitize_ui_error",
]
