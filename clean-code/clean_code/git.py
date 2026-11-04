import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
UNSAFE_PATH = re.compile(r"[\r\n]")


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
    added_lines: frozenset[int] = field(default_factory=frozenset)

    @property
    def mode_changed(self) -> bool:
        return self.modes[0] != self.modes[1]


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
        added = self._added_lines(revisions)
        fields = self.git("diff", "--raw", "-z", "-M", "--no-abbrev", revisions.base, revisions.head).split("\0")
        changes, index = [], 0
        while index < len(fields) - 1:
            old_mode, new_mode, _, _, status = fields[index].lstrip(":").split(" ")
            path_count = 2 if status[0] in "RC" else 1
            paths = fields[index + 1:index + 1 + path_count]
            index += 1 + path_count
            lines = frozenset(added.get(paths[-1], ()))
            changes.append(FileChange(status[0], paths[-1], paths[0], (old_mode, new_mode), lines))
        return changes

    def _added_lines(self, revisions: Revisions) -> dict[str, set[int]]:
        diff = self.git("diff", "--no-color", "--no-ext-diff", "-U0", "-M", "--dst-prefix=b/", revisions.base, revisions.head)
        added: dict[str, set[int]] = {}
        current: set[int] = set()
        for line in diff.splitlines():
            if line.startswith("+++ "):
                current = added.setdefault(line[6:], set()) if line.startswith("+++ b/") else set()
                continue
            hunk = HUNK.match(line)
            if hunk:
                start, count = int(hunk.group(1)), int(hunk.group(2) or 1)
                current.update(range(start, start + count))
        return added

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
        if len(header) != 3 or header[1] != b"blob":
            raise RuntimeError(f"unexpected git cat-file reply for {path!r}: {header!r}")
        size = int(header[2])
        yield path, output[offset:offset + size]
        offset += size + 1
    if offset != len(output):
        raise RuntimeError("git cat-file returned more objects than were requested")
