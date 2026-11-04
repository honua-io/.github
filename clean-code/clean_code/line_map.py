import re
from dataclasses import dataclass
from functools import cached_property

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int

    @classmethod
    def parse(cls, header: str) -> "Hunk | None":
        match = HUNK_HEADER.match(header)
        if not match:
            return None
        old_start, old_count, new_start, new_count = match.groups()
        return cls(int(old_start), int(old_count or 1), int(new_start), int(new_count or 1))

    @property
    def head_end(self) -> int:
        """First head line after this hunk; a pure deletion sits just after its new_start line."""
        return self.new_start + (self.new_count or 1)


@dataclass(frozen=True)
class LineMap:
    """How a file's head lines relate to its base lines, from a zero-context diff."""

    hunks: tuple[Hunk, ...] = ()

    @cached_property
    def added_lines(self) -> frozenset[int]:
        return frozenset(line for hunk in self.hunks for line in range(hunk.new_start, hunk.new_start + hunk.new_count))

    def base_line(self, head_line: int) -> int | None:
        """The base line an unchanged head line came from; None for an added line."""
        if head_line in self.added_lines:
            return None
        shift = sum(hunk.new_count - hunk.old_count for hunk in self.hunks if hunk.head_end <= head_line)
        return head_line - shift
