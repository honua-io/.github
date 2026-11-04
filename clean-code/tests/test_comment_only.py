import unittest
from pathlib import Path

from clean_code.comment_only import DocstringPolicy, compare_lexed, verify_diff
from clean_code.git import Revisions
from clean_code.lexing import lex_files
from clean_code.tokens import LexError
from tests.repo import ScratchRepository

FIXTURES = Path(__file__).parent / "fixtures" / "comment_only"


def fixture_verdict(case: Path) -> str | None:
    """Problem found between the case's base and head files, or None when the change is comment-only."""
    base, head = sorted(case.glob("base.*"))[0], sorted(case.glob("head.*"))[0]
    lexed = lex_files({f"base{base.suffix}": base.read_text(), f"head{head.suffix}": head.read_text()})
    sides = [lexed[f"base{base.suffix}"], lexed[f"head{head.suffix}"]]
    errors = [side for side in sides if isinstance(side, LexError)]
    if errors:
        return str(errors[0])
    policy = DocstringPolicy.REMOVABLE if case.name.endswith("-removable") else DocstringPolicy.CODE
    return compare_lexed(*sides, policy)


class FixtureCases(unittest.TestCase):
    def test_comment_only_fixtures_pass(self):
        for case in sorted(FIXTURES.glob("same-*")):
            with self.subTest(case.name):
                self.assertIsNone(fixture_verdict(case))

    def test_code_change_fixtures_fail(self):
        for case in sorted(FIXTURES.glob("diff-*")):
            with self.subTest(case.name):
                self.assertIsNotNone(fixture_verdict(case))

    def test_docstring_change_names_the_declaration(self):
        problem = fixture_verdict(FIXTURES / "diff-py-docstring-removed")
        self.assertIn("declare docstring removal", problem)


class DiffVerification(unittest.TestCase):
    def setUp(self):
        self.scratch = ScratchRepository()
        self.addCleanup(self.scratch.close)
        self.base = self.scratch.commit({"a.cs": "int a = 1; // one\n", "notes.md": "text\n", "gone.py": "x = 1\n"})

    def verdicts(self, files: dict[str, str | None]) -> dict[str, str | None]:
        head = self.scratch.commit(files)
        verdicts = verify_diff(self.scratch.repository, Revisions(self.base, head), DocstringPolicy.CODE)
        return {verdict.path: verdict.problem for verdict in verdicts}

    def test_comment_removal_passes(self):
        self.assertEqual(self.verdicts({"a.cs": "int a = 1;\n"}), {"a.cs": None})

    def test_added_deleted_and_unlexable_files_fail(self):
        problems = self.verdicts({"new.cs": "// x\n", "gone.py": None, "notes.md": "other\n"})
        self.assertEqual(set(problems), {"new.cs", "gone.py", "notes.md"})
        self.assertTrue(all(problems.values()))

    def test_code_change_fails_with_location(self):
        problem = self.verdicts({"a.cs": "int a = 2; // one\n"})["a.cs"]
        self.assertIn("line 1", problem)


if __name__ == "__main__":
    unittest.main()
