"""Pairs each head function with at most one base function, and each base function with at most one head function.

In order: shared unchanged lines that each function owns directly (not through a nested function), then a unique
same name, then similar text. A head function left unpaired is new; of a function split in two, only one half
continues it.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from difflib import SequenceMatcher

from .git import FileChange
from .tokens import Function

MINIMUM_SIMILARITY = 0.75


@dataclass(frozen=True)
class FileFunctions:
    functions: list[Function]
    lines: list[str]

    def owned_lines(self, function: Function) -> set[int]:
        """The function's lines that no function nested inside it claims."""
        nested = [other for other in self.functions if other != function and function.start <= other.start
                  and other.end <= function.end and (other.start, other.end) != (function.start, function.end)]
        claimed = {line for other in nested for line in range(other.start, other.end + 1)}
        return set(range(function.start, function.end + 1)) - claimed

    def text(self, function: Function) -> str:
        return "\n".join(line.strip() for line in self.lines[function.start - 1:function.end])


def pair_functions(change: FileChange, head: FileFunctions, base: FileFunctions) -> dict[Function, Function]:
    pairs: dict[Function, Function] = {}
    _assign(pairs, _unchanged_line_scores(change, head, base))
    _assign(pairs, _unique_name_scores(head, base, pairs))
    _assign(pairs, _similarity_scores(head, base, pairs))
    return pairs


def _assign(pairs: dict[Function, Function], scored: Iterator[tuple[float, Function, Function]]) -> None:
    """Greedy one-to-one assignment, best score first, skipping functions already paired."""
    taken = set(pairs.values())
    for _, head_function, base_function in sorted(scored, key=lambda entry: entry[0], reverse=True):
        if head_function not in pairs and base_function not in taken:
            pairs[head_function] = base_function
            taken.add(base_function)


def _unchanged_line_scores(change: FileChange, head: FileFunctions, base: FileFunctions):
    base_owned = {function: base.owned_lines(function) for function in base.functions}
    for head_function in head.functions:
        images = {change.line_map.base_line(line) for line in head.owned_lines(head_function)} - {None}
        for base_function, owned in base_owned.items():
            if shared := len(images & owned):
                yield shared, head_function, base_function


def _unique_name_scores(head: FileFunctions, base: FileFunctions, pairs: dict[Function, Function]):
    free_base = [function for function in base.functions if function not in set(pairs.values())]
    for head_function in head.functions:
        same_name = [function for function in free_base if function.name == head_function.name]
        if head_function not in pairs and len(same_name) == 1:
            yield 1.0, head_function, same_name[0]


def _similarity_scores(head: FileFunctions, base: FileFunctions, pairs: dict[Function, Function]):
    free_base = [function for function in base.functions if function not in set(pairs.values())]
    for head_function in (function for function in head.functions if function not in pairs):
        for base_function in free_base:
            ratio = SequenceMatcher(None, head.text(head_function), base.text(base_function)).ratio()
            if ratio >= MINIMUM_SIMILARITY:
                yield ratio, head_function, base_function


def enclosing_function(line: int, functions: list[Function]) -> Function | None:
    containing = [function for function in functions if function.start <= line <= function.end]
    return min(containing, key=lambda function: function.length, default=None)
