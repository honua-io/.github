import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class Revisions:
    base: str
    head: str


@dataclass(frozen=True)
class FileChange:
    status: str
    path: str
    old_path: str
    added_lines: frozenset[int] = field(default_factory=frozenset)


class Repository:
    def __init__(self, root: Path):
        self.root = root

    def git(self, *args: str, stdin: str | None = None) -> str:
        done = subprocess.run(
            ["git", "-c", "core.quotePath=false", *args],
            cwd=self.root, input=stdin, capture_output=True, text=True, check=False,
        )
        if done.returncode:
            raise RuntimeError(f"git {' '.join(args[:2])} failed: {done.stderr.strip()}")
        return done.stdout

    def changes(self, revisions: Revisions) -> list[FileChange]:
        added = self._added_lines(revisions)
        entries = self.git("diff", "--name-status", "-z", "-M", revisions.base, revisions.head).split("\0")
        changes, index = [], 0
        while index < len(entries) - 1:
            status = entries[index][0]
            paths = entries[index + 1:index + (3 if status in "RC" else 2)]
            index += 1 + len(paths)
            changes.append(FileChange(status, paths[-1], paths[0], frozenset(added.get(paths[-1], ()))))
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

    def read(self, revision: str, paths: list[str]) -> dict[str, str]:
        """Contents of paths at revision; paths absent there are left out."""
        if not paths:
            return {}
        request = "".join(f"{revision}:{path}\n" for path in paths)
        done = subprocess.run(
            ["git", "cat-file", "--batch"], cwd=self.root, input=request.encode(), capture_output=True, check=True
        )
        return dict(_parse_batch(done.stdout, paths))

    def paths(self, revision: str) -> list[str]:
        return [path for path in self.git("ls-tree", "-r", "-z", "--name-only", revision).split("\0") if path]


def _parse_batch(output: bytes, paths: list[str]):
    offset = 0
    for path in paths:
        header_end = output.index(b"\n", offset)
        header = output[offset:header_end].split()
        offset = header_end + 1
        if header[-1] == b"missing" or header[1] != b"blob":
            continue
        size = int(header[2])
        yield path, output[offset:offset + size].decode("utf-8", errors="replace")
        offset += size + 1
