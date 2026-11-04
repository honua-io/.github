"""Pairs a head function with the base function it came from, through the lines the diff left unchanged."""

from .git import FileChange
from .tokens import Function


def base_counterpart(head: Function, change: FileChange, base_functions: list[Function]) -> Function | None:
    """The base function holding most of head's unchanged lines (the innermost on a tie); None if head is new."""
    images = [change.line_map.base_line(line) for line in range(head.start, head.end + 1)]
    images = [line for line in images if line is not None]
    scored = [(sum(base.start <= line <= base.end for line in images), -base.length, base) for base in base_functions]
    best = max(scored, key=lambda entry: entry[:2], default=None)
    return best[2] if best and best[0] else None


def enclosing_function(line: int, functions: list[Function]) -> Function | None:
    containing = [function for function in functions if function.start <= line <= function.end]
    return min(containing, key=lambda function: function.length, default=None)
