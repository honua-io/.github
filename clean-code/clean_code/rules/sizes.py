"""Chapter 10: classes and files stay small. New files have a budget; files over the large budget may not grow much."""

from collections.abc import Iterator

from ..budgets import BUDGETS
from ..context import CheckContext
from ..findings import Finding, Location
from ..paths import matches_any


def check_sizes(context: CheckContext) -> Iterator[Finding]:
    for change in context.changes:
        lines = _line_count(context.head_texts.get(change.path, ""))
        base_text = context.base_texts.get(change.path)
        location = Location(change.path, 1)
        if base_text is None and lines > BUDGETS.new_file_lines:
            yield Finding.of("clean-code/new-file-size", location, f"{lines} lines; split it by responsibility")
            continue
        growth = lines - _line_count(base_text or "")
        if base_text is not None and lines > BUDGETS.large_file_lines and growth >= BUDGETS.large_file_growth_lines:
            message = f"grew by {growth} to {lines} lines; extract the new code instead"
            yield Finding.of("clean-code/large-file-growth", location, message)


def check_frozen_files(context: CheckContext) -> Iterator[Finding]:
    """Files the caller froze (e.g. hand-copied DTO shims awaiting a migration) may not be added or grow."""
    for change in context.changes:
        if not matches_any(change.path, context.options.frozen):
            continue
        lines = _line_count(context.head_texts.get(change.path, ""))
        base_text = context.base_texts.get(change.path)
        if base_text is None or lines > _line_count(base_text):
            grew = "new" if base_text is None else f"grew from {_line_count(base_text)} to {lines} lines"
            yield Finding.of("clean-code/frozen-file", Location(change.path, 1), f"{grew}; this file is frozen")


def _line_count(text: str) -> int:
    """Lines as git counts them: ended by LF only."""
    lines = text.split("\n")
    return len(lines) - (lines[-1] == "")
