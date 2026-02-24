"""Formatting helpers for hallucination detection output."""

from __future__ import annotations

from cloakroom.models import HallucinationFlag


def format_hallucination_flags(flags: list[HallucinationFlag]) -> str:
    """Format hallucination flags as a concise, user-facing block."""
    lines: list[str] = []
    for flag in flags:
        if flag.flag_type == "mutated" and flag.nearest_match:
            lines.append(
                f"[WARNING MUTATED: {flag.token_text} -> {flag.nearest_match}]"
            )
        elif flag.flag_type == "dropped":
            lines.append(f"[WARNING DROPPED TOKEN: {flag.token_text}]")
        else:
            lines.append(f"[WARNING AI GENERATED: {flag.token_text}]")
    return "\n".join(lines)

