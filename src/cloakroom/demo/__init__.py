"""Demo sample fixtures and helpers for the killer-demo workflow."""

from __future__ import annotations

from importlib import resources


def load_sample(name: str) -> str:
    """Return the text of a demo sample bundled with the package."""
    return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")
