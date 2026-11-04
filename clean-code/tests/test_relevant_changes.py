import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.repo import ScratchRepository

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "relevant-changes.yml"


def match_script() -> str:
    """The workflow's `run:` body, so the tests exercise exactly what CI runs."""
    lines = WORKFLOW.read_text().splitlines()
    start = next(index for index, line in enumerate(lines) if line.strip() == "run: |") + 1
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = [line for line in lines[start:] if not line.strip() or len(line) - len(line.lstrip()) >= indent]
    return textwrap.dedent("\n".join(body))


class RelevantChanges(unittest.TestCase):
    """The detector says relevant=true or false, and fails rather than guess when its pattern file is unusable."""

    def setUp(self):
        self.scratch = ScratchRepository()
        self.addCleanup(self.scratch.close)
        self.base = self.scratch.commit({"src/app.py": "x = 1\n", "docs/readme.md": "doc\n"})

    def run_match(self, patterns: str | None, base: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as scratch:
            output, patterns_file = Path(scratch, "output"), Path(scratch, "patterns.txt")
            if patterns is not None:
                patterns_file.write_text(patterns)
            env = {**os.environ, "BASE": base, "PATTERNS_FILE": str(patterns_file), "GITHUB_OUTPUT": str(output)}
            done = subprocess.run(["bash", "-e", "-c", match_script()], cwd=self.scratch.root, env=env,
                                  capture_output=True, text=True, check=False)
            return done.returncode, output.read_text() if output.exists() else ""

    def test_a_listed_path_is_relevant_and_others_are_not(self):
        self.scratch.commit({"src/app.py": "x = 2\n"})
        self.assertEqual(self.run_match("# comment\n\n  src/**  \n", self.base), (0, "relevant=true\n"))
        self.assertEqual(self.run_match("docs/**\n", self.base), (0, "relevant=false\n"))

    def test_runs_without_a_base_are_always_relevant(self):
        for base in ("", "0" * 40):
            with self.subTest(base=base):
                self.assertEqual(self.run_match("never/**\n", base), (0, "relevant=true\n"))

    def test_unusable_pattern_files_fail_without_an_answer(self):
        for patterns in (None, "", "# only a comment\n\n"):
            with self.subTest(patterns=patterns):
                code, output = self.run_match(patterns, self.base)
                self.assertNotEqual(code, 0)
                self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
