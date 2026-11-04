"""Chapter 10: classes and files stay small. New files have a budget; files already over the large budget may not grow."""

from collections.abc import Iterator

from ..budgets import BUDGETS
from ..context import CheckContext
from ..findings import Finding, Location


def check_sizes(context: CheckContext) -> Iterator[Finding]:
    for change in context.changes:
        lines = _line_count(context.head_texts.get(change.path, ""))
        base_text = context.base_texts.get(change.path)
        location = Location(change.path, 1)
        if base_text is None and lines > BUDGETS.new_file_lines:
            yield Finding.of("clean-code/new-file-size", location, f"{lines} lines; split it by responsibility")
            continue
        base_lines = _line_count(base_text or "")
        if base_text is not None and lines > BUDGETS.large_file_lines and lines > base_lines:
            message = f"grew from {base_lines} to {lines} lines; extract the new code instead"
            yield Finding.of("clean-code/large-file-growth", location, message)


def _line_count(text: str) -> int:
    """Lines as git counts them: ended by LF only."""
    lines = text.split("\n")
    return len(lines) - (lines[-1] == "")
