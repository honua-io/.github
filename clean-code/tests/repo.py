import subprocess
import tempfile
from pathlib import Path

from clean_code.git import Repository


class ScratchRepository:
    """A throwaway git repository with a base commit and a head commit."""

    def __init__(self):
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self._git("init", "-q", "-b", "trunk")
        self._git("config", "user.email", "test@example.org")
        self._git("config", "user.name", "Test")
        self.repository = Repository(self.root)

    def commit(self, files: dict[str, str | None]) -> str:
        for path, text in files.items():
            target = self.root / path
            if text is None:
                target.unlink()
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        self._git("add", "-A")
        self._git("commit", "-q", "--allow-empty", "-m", "change")
        return self._git("rev-parse", "HEAD").strip()

    def close(self) -> None:
        self._directory.cleanup()

    def _git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, text=True).stdout
