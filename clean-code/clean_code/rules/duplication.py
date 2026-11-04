"""G5: blocks touched by the PR whose copies at head outnumber those at base, so the PR introduced a clone.
Moving a block keeps the count, so it is not a clone."""

import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass

from ..budgets import BUDGETS
from ..context import CheckContext, readable_texts
from ..findings import Finding, Location
from ..lexing import language_of
from ..paths import GENERATED_OR_VENDORED, matches_any

TOKEN = re.compile(r"\w+|[^\w\s]")
TRIVIAL_LINE = re.compile(r"^(?:[^\w]*|(?:using|import|from|#include|require)\b.*|//.*|#.*|\*.*|/\*.*)$")


@dataclass(frozen=True, order=True)
class _Window:
    path: str
    first_line: int
    last_line: int


class _SignificantLines:
    """A file's non-trivial lines, normalized, with their line numbers and token counts."""

    def __init__(self, text: str, language: str):
        self.language = language
        stripped = ((number, line.strip()) for number, line in enumerate(text.split("\n"), 1))
        kept = [(number, line) for number, line in stripped if not TRIVIAL_LINE.match(line)]
        self.numbers = [number for number, _ in kept]
        self.hashes = [hash(line) for _, line in kept]
        self.tokens = [len(TOKEN.findall(line)) for _, line in kept]

    def windows(self) -> Iterator[tuple[int, int]]:
        """(index, hash) of every run of duplicate_lines consecutive significant lines."""
        size = BUDGETS.duplicate_lines
        for index in range(len(self.hashes) - size + 1):
            yield index, hash((self.language, tuple(self.hashes[index:index + size])))

    def window(self, path: str, index: int) -> _Window:
        return _Window(path, self.numbers[index], self.numbers[index + BUDGETS.duplicate_lines - 1])

    def is_substantial(self, index: int) -> bool:
        return sum(self.tokens[index:index + BUDGETS.duplicate_lines]) >= BUDGETS.duplicate_tokens


def check_duplication(context: CheckContext) -> Iterator[Finding]:
    candidates = _added_windows(context)
    if not candidates:
        return
    at_head = _occurrences(context, context.revisions.head, set(candidates))
    at_base = _occurrences(context, context.revisions.base, set(candidates))
    introduced = {key: windows for key, windows in candidates.items() if len(at_head[key]) > len(at_base[key])}
    for path, regions in _clone_regions(introduced, at_head).items():
        for first_line, other in regions:
            message = f"repeats {other.path}:{other.first_line}; extract a shared helper"
            yield Finding.of("clean-code/duplication", Location(path, first_line), message)


def _added_windows(context: CheckContext) -> dict[int, list[_Window]]:
    candidates: dict[int, list[_Window]] = defaultdict(list)
    for change in context.changes:
        lines = _SignificantLines(context.head_texts.get(change.path, ""), language_of(change.path).name)
        for index, window_hash in lines.windows():
            window = lines.window(change.path, index)
            span = lines.numbers[index:index + BUDGETS.duplicate_lines]
            if any(number in change.added_lines for number in span) and lines.is_substantial(index):
                candidates[window_hash].append(window)
    return candidates


def _occurrences(context: CheckContext, revision: str, wanted: set[int]) -> dict[int, list[_Window]]:
    languages = {language_of(change.path).name for change in context.changes}
    excludes = GENERATED_OR_VENDORED + context.options.excludes
    paths = [path for path in context.repository.paths(revision) if _is_peer(path, languages, excludes)]
    found: dict[int, list[_Window]] = defaultdict(list)
    for path, text in readable_texts(context.repository, revision, paths).items():
        lines = _SignificantLines(text, language_of(path).name)
        for index, window_hash in lines.windows():
            if window_hash in wanted:
                found[window_hash].append(lines.window(path, index))
    return found


def _is_peer(path: str, languages: set[str], excludes: tuple[str, ...]) -> bool:
    language = language_of(path)
    return language is not None and language.name in languages and not matches_any(path, excludes)


def _clone_regions(candidates, occurrences) -> dict[str, list[tuple[int, _Window]]]:
    """First line of each run of overlapping duplicated windows per file, with one other copy."""
    regions: dict[str, list[tuple[int, _Window]]] = defaultdict(list)
    covered_until: dict[str, int] = defaultdict(int)
    for window, other in sorted(_first_copies(candidates, occurrences)):
        if window.first_line > covered_until[window.path]:
            regions[window.path].append((window.first_line, other))
        covered_until[window.path] = max(covered_until[window.path], window.last_line)
    return regions


def _first_copies(candidates, occurrences) -> Iterator[tuple[_Window, _Window]]:
    for window_hash, windows in candidates.items():
        for window in windows:
            other = next((copy for copy in occurrences.get(window_hash, []) if not _overlaps(window, copy)), None)
            if other:
                yield window, other


def _overlaps(window: _Window, other: _Window) -> bool:
    return window.path == other.path and window.first_line <= other.last_line and other.first_line <= window.last_line
