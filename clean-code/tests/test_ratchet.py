import os
import unittest

from tests.test_rules import PullRequest, numbered_lines, rule_keys

TICKET = "// Fixes #1234.\nint retries = 3;\n"


def python_function(name: str, body_lines: int) -> str:
    return f"def {name}():\n" + numbered_lines(body_lines, "    step_{0}()") + "    return 1\n"


class FunctionRatchet(unittest.TestCase):
    def setUp(self):
        self.pull_request = PullRequest({"src/at_budget.py": python_function("at_budget", 58),
                                         "src/legacy.py": python_function("legacy", 98),
                                         "src/wide.py": "def wide(a, b, c, d, e):\n    return a\n"})
        self.addCleanup(self.pull_request.close)

    def keys(self, files: dict[str, str]) -> set[str]:
        return rule_keys(self.pull_request.findings(files))

    def test_growing_a_function_past_the_budget_is_flagged(self):
        self.assertIn("clean-code/function-length", self.keys({"src/at_budget.py": python_function("at_budget", 60)}))

    def test_touching_an_oversized_function_without_growing_it_is_not(self):
        edited = python_function("legacy", 98).replace("step_3()", "step_three()")
        self.assertNotIn("clean-code/function-length", self.keys({"src/legacy.py": edited}))

    def test_growing_an_oversized_function_is_flagged(self):
        self.assertIn("clean-code/function-length", self.keys({"src/legacy.py": python_function("legacy", 99)}))

    def test_existing_tool_findings_are_not_reported_again(self):
        edited = "def wide(a, b, c, d, e):\n    return b\n"
        self.assertNotIn("ruff/PLR0913", self.keys({"src/wide.py": edited}))

    def test_a_parameter_added_on_a_continuation_line_is_flagged(self):
        pull_request = PullRequest({"src/narrow.py": "def narrow(\n    a, b, c, d,\n):\n    return a\n"})
        self.addCleanup(pull_request.close)
        widened = "def narrow(\n    a, b, c, d,\n    e,\n):\n    return a\n"
        self.assertIn("ruff/PLR0913", rule_keys(pull_request.findings({"src/narrow.py": widened})))


class DuplicationRatchet(unittest.TestCase):
    def setUp(self):
        self.block = numbered_lines(16, "value_{0} = compute({0}, offset_{0}, scale)")
        self.pull_request = PullRequest({"src/a.py": "first = 1\n" + self.block, "src/b.py": self.block,
                                         "src/c.py": "keep = 1\n"})
        self.addCleanup(self.pull_request.close)

    def keys(self, files: dict[str, str | None]) -> set[str]:
        return rule_keys(self.pull_request.findings(files))

    def test_moving_a_block_while_another_copy_remains_is_not_a_new_clone(self):
        self.assertNotIn("clean-code/duplication", self.keys({"src/a.py": "first = 1\n", "src/c.py": "keep = 1\n" + self.block}))

    def test_copying_a_block_is_a_new_clone(self):
        self.assertIn("clean-code/duplication", self.keys({"src/c.py": "keep = 1\n" + self.block}))

    def test_the_same_lines_in_another_language_are_not_a_clone(self):
        csharp = numbered_lines(16, "value_{0} = compute({0}, offset_{0}, scale);")
        python = numbered_lines(16, "value_{0} = compute({0}, offset_{0}, scale);")
        self.assertNotIn("clean-code/duplication", self.keys({"src/New.cs": csharp, "src/new.py": python}))


class UnusualPaths(unittest.TestCase):
    def test_paths_git_quotes_or_tab_terminates_are_still_checked(self):
        pull_request = PullRequest({"README.md": "x\n"})
        self.addCleanup(pull_request.close)
        paths = ["src/with space.cs", 'src/with"quote.cs', "src/with\ttab.cs", "src/café.cs"]
        found = pull_request.findings(dict.fromkeys(paths, TICKET))
        self.assertEqual({finding.location.path for finding in found}, set(paths))

    def test_a_symlink_replaced_by_source_is_checked(self):
        pull_request = PullRequest({"target.cs": "int a = 1;\n"})
        self.addCleanup(pull_request.close)
        root = pull_request.scratch.root
        os.symlink("target.cs", root / "source.cs")
        pull_request.base = pull_request.scratch.commit({})
        (root / "source.cs").unlink()
        self.assertIn("clean-code/ticket-reference", rule_keys(pull_request.findings({"source.cs": TICKET})))


if __name__ == "__main__":
    unittest.main()
