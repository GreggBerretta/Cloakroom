"""Public pipeline API exports."""

from cowork_shield.pipeline.ui_api import (
    UIOperationResult,
    anonymize_file,
    get_workspaces,
    get_file_columns,
    preview_entities,
    render_entity_table,
    sanitize_ui_error,
    restore_file,
)
from cowork_shield.pipeline.columns import inspect_columns

__all__ = [
    "UIOperationResult",
    "anonymize_file",
    "restore_file",
    "preview_entities",
    "render_entity_table",
    "get_workspaces",
    "get_file_columns",
    "inspect_columns",
    "sanitize_ui_error",
]
