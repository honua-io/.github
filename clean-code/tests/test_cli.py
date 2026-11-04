import subprocess
import sys
import unittest
from pathlib import Path

from tests.repo import ScratchRepository

CHECK = Path(__file__).resolve().parents[1] / "check_clean_code.py"


class DeclaredCommentOnly(unittest.TestCase):
    def setUp(self):
        self.scratch = ScratchRepository()
        self.addCleanup(self.scratch.close)
        self.base = self.scratch.commit({"a.cs": "int a = 1; // one\n"})
        self.body = self.scratch.root.parent / f"{self.scratch.root.name}-body.md"
        self.addCleanup(self.body.unlink, missing_ok=True)

    def exit_code(self, head_text: str, pr_body: str) -> int:
        head = self.scratch.commit({"a.cs": head_text})
        self.body.write_text(pr_body)
        command = [sys.executable, "-I", str(CHECK), "--repo", str(self.scratch.root), "--base", self.base,
                   "--head", head, "--pr-body", str(self.body)]
        return subprocess.run(command, capture_output=True, text=True, check=False).returncode

    def test_proven_comment_only_change_passes(self):
        self.assertEqual(self.exit_code("int a = 1;\n", "clean-code: comment-only\n"), 0)

    def test_disproved_declaration_fails_even_with_an_exception(self):
        body = "clean-code: comment-only\nquality-exception: bulk cleanup\n"
        self.assertEqual(self.exit_code("int a = 2;\n", body), 1)

    def test_code_change_without_declaration_passes(self):
        self.assertEqual(self.exit_code("int a = 2;\n", "Mentions `clean-code: comment-only` in prose.\n"), 0)


if __name__ == "__main__":
    unittest.main()
