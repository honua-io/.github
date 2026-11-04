import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .line_map import Hunk, LineMap

UNSAFE_PATH = re.compile(r"[\r\n]")
REGULAR_FILE_MODES = frozenset({"100644", "100755"})
C_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}


class UnreadableFile(ValueError):
    pass


@dataclass(frozen=True)
class Revisions:
    base: str
    head: str


@dataclass(frozen=True)
class FileChange:
    status: str
    path: str
    old_path: str
    modes: tuple[str, str] = ("100644", "100644")
    line_map: LineMap = field(default_factory=LineMap)

    @property
    def added_lines(self) -> frozenset[int]:
        return self.line_map.added_lines

    @property
    def mode_changed(self) -> bool:
        return self.modes[0] != self.modes[1]

    @property
    def head_is_regular_file(self) -> bool:
        return self.modes[1] in REGULAR_FILE_MODES

    @property
    def base_is_regular_file(self) -> bool:
        return self.modes[0] in REGULAR_FILE_MODES

    @property
    def is_regular_file(self) -> bool:
        """False for symlinks and submodules, whose blobs are link targets or commit ids, not source."""
        return self.modes[1] in REGULAR_FILE_MODES and self.modes[0] in REGULAR_FILE_MODES | {"000000"}


class Repository:
    def __init__(self, root: Path):
        self.root = root

    def git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", "-c", "core.quotePath=false", *args],
            cwd=self.root, capture_output=True, text=True, errors="surrogateescape", check=False,
        )
        if done.returncode:
            raise RuntimeError(f"git {' '.join(args[:2])} failed: {done.stderr.strip()}")
        return done.stdout

    def changes(self, revisions: Revisions) -> list[FileChange]:
        hunks = self._hunks(revisions)
        fields = self.git("diff", "--raw", "-z", "-M", "--no-abbrev", revisions.base, revisions.head).split("\0")
        changes, index = [], 0
        while index < len(fields) - 1:
            old_mode, new_mode, _, _, status = fields[index].lstrip(":").split(" ")
            path_count = 2 if status[0] in "RC" else 1
            paths = fields[index + 1:index + 1 + path_count]
            index += 1 + path_count
            line_map = LineMap(tuple(hunks.get(paths[-1], ())))
            changes.append(FileChange(status[0], paths[-1], paths[0], (old_mode, new_mode), line_map))
        return changes

    def _hunks(self, revisions: Revisions) -> dict[str, list[Hunk]]:
        diff = self.git("diff", "--no-color", "--no-ext-diff", "-U0", "-M", "--dst-prefix=b/", revisions.base, revisions.head)
        hunks: dict[str, list[Hunk]] = {}
        current: list[Hunk] = []
        for line in diff.split("\n"):
            if line.startswith("+++ "):
                path = _diff_header_path(line[4:])
                current = hunks.setdefault(path[2:], []) if path.startswith("b/") else []
                continue
            hunk = Hunk.parse(line)
            if hunk:
                current.append(hunk)
        return hunks

    def read(self, revision: str, paths: list[str]) -> dict[str, str | UnreadableFile]:
        """UTF-8 contents of paths at revision; paths absent there are left out, undecodable ones are errors."""
        readable = [path for path in paths if not UNSAFE_PATH.search(path)]
        unsafe = {path: UnreadableFile("path contains a line break") for path in paths if UNSAFE_PATH.search(path)}
        if not readable:
            return unsafe
        request = "".join(f"{revision}:{path}\n" for path in readable)
        done = subprocess.run(
            ["git", "cat-file", "--batch"], cwd=self.root, input=request.encode(), capture_output=True, check=True
        )
        return unsafe | {path: _decode(blob) for path, blob in _parse_batch(done.stdout, readable)}

    def paths(self, revision: str) -> list[str]:
        return [path for path in self.git("ls-tree", "-r", "-z", "--name-only", revision).split("\0") if path]


def _diff_header_path(field: str) -> str:
    """A ---/+++ path as git writes it: C-quoted when it has special characters, tab-terminated when it has spaces."""
    if not field.startswith('"'):
        return field.removesuffix("\t")
    raw, index = bytearray(), 1
    while index < len(field) and field[index] != '"':
        index = _unescape_into(raw, field, index)
    return raw.decode("utf-8", errors="surrogateescape")


def _unescape_into(raw: bytearray, field: str, index: int) -> int:
    if field[index] != "\\":
        raw += field[index].encode("utf-8", errors="surrogateescape")
        return index + 1
    escape = field[index + 1]
    if escape in C_ESCAPES:
        raw.append(C_ESCAPES[escape])
        return index + 2
    raw.append(int(field[index + 1:index + 4], 8))
    return index + 4


def _decode(blob: bytes) -> str | UnreadableFile:
    try:
        return blob.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        return UnreadableFile(f"not UTF-8: {error.reason} at byte {error.start}")


def _parse_batch(output: bytes, paths: list[str]):
    offset = 0
    for path in paths:
        header_end = output.index(b"\n", offset)
        header = output[offset:header_end].split()
        offset = header_end + 1
        if header[-1] == b"missing":
            continue
        size = int(header[2]) if len(header) == 3 and header[1] == b"blob" and header[2].isdigit() else -1
        if size < 0 or output[offset + size:offset + size + 1] != b"\n":
            raise RuntimeError(f"unexpected git cat-file reply for {path!r}: {header!r}")
        yield path, output[offset:offset + size]
        offset += size + 1
    if offset != len(output):
        raise RuntimeError("git cat-file returned more objects than were requested")
