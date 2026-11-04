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


def csharp_method(signature: str, body_lines: int) -> str:
    return f"    {signature}\n    {{\n" + numbered_lines(body_lines, "        Step{0}();") + "    }\n"


def csharp_class(*methods: str) -> str:
    return "class Worker\n{\n" + "".join(methods) + "}\n"


class Correspondence(unittest.TestCase):
    """Each head function is judged against the base function its unchanged lines came from."""

    def findings(self, base: dict[str, str], head: dict[str, str]) -> set[str]:
        pull_request = PullRequest(base)
        self.addCleanup(pull_request.close)
        return rule_keys(pull_request.findings(head))

    def test_an_overload_cannot_borrow_a_longer_overloads_baseline(self):
        long_overload = csharp_method("void Process(int count)", 78)
        base = csharp_class(csharp_method("void Process(string text)", 57), long_overload)
        head = csharp_class(csharp_method("void Process(string text)", 59), long_overload)
        self.assertIn("clean-code/function-length", self.findings({"src/Worker.cs": base}, {"src/Worker.cs": head}))

    def test_a_new_overload_does_not_inherit_flags_or_parameter_budget(self):
        base = csharp_class(csharp_method("void Process(bool force)", 1), csharp_method("void Run(int a, int b, int c, int d, int e, int f)", 1))
        head = base.replace("}\n}\n", "}\n" + csharp_method("void Process(string text, bool force)", 1)
                            + csharp_method("void Run(int a, int b, int c, int d, int e)", 1) + "}\n", 1)
        found = self.findings({"src/Worker.cs": base}, {"src/Worker.cs": head})
        self.assertTrue({"clean-code/flag-argument", "clean-code/too-many-parameters"} <= found, found)

    def test_renames_keep_their_baseline(self):
        base = {"src/legacy.py": python_function("legacy", 68), "src/flags.py": "def run(*, force: bool):\n    return 1\n"}
        head = {"src/legacy.py": python_function("publish", 68), "src/flags.py": "def run(*, enabled: bool):\n    return 1\n"}
        found = self.findings(base, head)
        self.assertFalse({"clean-code/function-length", "clean-code/flag-argument"} & found, found)

    def test_quoted_boolean_annotation_is_a_flag(self):
        found = self.findings({"README.md": "x\n"}, {"src/work.py": 'def work(*, force: "bool"):\n    return 1\n'})
        self.assertIn("clean-code/flag-argument", found)


class LinterCorrespondence(unittest.TestCase):
    def findings(self, base: dict[str, str], head: dict[str, str]) -> set[str]:
        pull_request = PullRequest(base)
        self.addCleanup(pull_request.close)
        return rule_keys(pull_request.findings(head))

    def test_a_violation_moving_between_same_named_methods_is_new(self):
        legacy = "class Legacy:\n    def process(\n        self, a, b, c, d, e,\n    ):\n        return a\n"
        fresh = "class New:\n    def process(\n        self, a, b, c, d,\n    ):\n        return a\n"
        head = legacy.replace("d, e,", "d,") + fresh.replace("c, d,", "c, d, e,")
        self.assertIn("ruff/PLR0913", self.findings({"src/m.py": legacy + fresh}, {"src/m.py": head}))

    def test_eslint_violation_moving_between_methods_is_new(self):
        base = "export class A {\n  run(\n    a: number, b: number, c: number, d: number, e: number,\n  ) { return a; }\n}\n" \
               "export class B {\n  run(\n    a: number, b: number, c: number, d: number,\n  ) { return a; }\n}\n"
        head = base.replace("d: number, e: number,", "d: number,", 1).replace(
            "    a: number, b: number, c: number, d: number,\n  ) { return a; }\n}\n",
            "    a: number, b: number, c: number, d: number, e: number,\n  ) { return a; }\n}\n")
        self.assertIn("eslint/max-params", self.findings({"src/m.ts": base}, {"src/m.ts": head}))

    def test_a_worsened_measure_is_new_and_a_renamed_parameter_is_not(self):
        base = "def wide(\n    a, b, c, d, e,\n):\n    return b\n"
        self.assertIn("ruff/PLR0913", self.findings({"src/w.py": base}, {"src/w.py": base.replace("e,", "e, f,")}))
        self.assertNotIn("ruff/PLR0913", self.findings({"src/w.py": base}, {"src/w.py": base.replace("a, b", "alpha, b")}))

    def test_renaming_a_typescript_parameter_is_not_new(self):
        base = "export function wide(a: number, b: number, c: number, d: number, e: number) {\n  return b;\n}\n"
        renamed = base.replace("(a: number", "(alpha: number")
        self.assertNotIn("eslint/max-params", self.findings({"src/w.ts": base}, {"src/w.ts": renamed}))


class OneToOnePairing(unittest.TestCase):
    """A base function's allowance continues in at most one head function."""

    def findings(self, base: dict[str, str], head: dict[str, str]) -> set[str]:
        pull_request = PullRequest(base)
        self.addCleanup(pull_request.close)
        return rule_keys(pull_request.findings(head))

    def test_splitting_a_function_makes_the_other_half_new(self):
        base = "def original(force: bool):\n    prepare()\n    publish()\n    return 1\n"
        head = "def first(force: bool):\n    prepare()\n\n\ndef second(force: bool):\n    publish()\n    return 1\n"
        self.assertIn("clean-code/flag-argument", self.findings({"src/s.py": base}, {"src/s.py": head}))

    def test_a_new_nested_function_does_not_inherit_its_parents_flags(self):
        base = "def outer(force: bool):\n    if force:\n        return 1\n    return 0\n"
        head = base.replace("    if force:", "    def inner(enabled: bool):")
        self.assertIn("clean-code/flag-argument", self.findings({"src/n.py": base}, {"src/n.py": head}))

    def test_splitting_a_csharp_method_does_not_reuse_its_parameter_budget(self):
        base = csharp_class("    void Original(int a, int b, int c, int d, int e, int f)\n    {\n        Prepare();\n        Publish();\n    }\n")
        head = csharp_class("    void First(int a, int b, int c, int d, int e)\n    {\n        Prepare();\n    }\n",
                            "    void Second(int a, int b, int c, int d, int e)\n    {\n        Publish();\n    }\n")
        self.assertIn("clean-code/too-many-parameters", self.findings({"src/W.cs": base}, {"src/W.cs": head}))

    def test_rewritten_or_reordered_functions_keep_their_baseline(self):
        base = {"src/r.py": "def work(a, b, c, d, e):\n    return a\n",
                "src/o.py": "def first(a, b, c, d, e):\n    return a\n\n\ndef second(x):\n    return x\n",
                "src/t.ts": "export function process(a: number, b: number, c: number, d: number, e: number) { return b; }\n"}
        head = {"src/r.py": "def work(alpha, b, c, d, e):\n    return alpha\n",
                "src/o.py": "def second(x):\n    return x\n\n\ndef first(a, b, c, d, e):\n    return a\n",
                "src/t.ts": base["src/t.ts"].replace("(a: number", "(alpha: number")}
        found = self.findings(base, head)
        self.assertFalse({"ruff/PLR0913", "eslint/max-params"} & found, found)


class Measures(unittest.TestCase):
    def findings(self, base: dict[str, str], head: dict[str, str]) -> set[str]:
        pull_request = PullRequest(base)
        self.addCleanup(pull_request.close)
        return rule_keys(pull_request.findings(head))

    def test_digits_in_a_function_name_do_not_hide_worsening(self):
        base = "export function process2(\n  a: number, b: number, c: number, d: number, e: number,\n) {\n  return a;\n}\n"
        head = base.replace("e: number,", "e: number, f: number,")
        self.assertIn("eslint/max-params", self.findings({"src/p.ts": base}, {"src/p.ts": head}))

    def test_growing_complexity_is_new(self):
        branches = "".join(f"    if x == {index}:\n        return {index}\n" for index in range(11))
        base = "def process2(x):\n" + branches + "    return -1\n"
        head = base.replace("    return -1\n", "    if x == 99:\n        return 99\n    return -1\n")
        self.assertIn("ruff/C901", self.findings({"src/c.py": base}, {"src/c.py": head}))


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

    def test_completing_a_clone_with_one_line_is_new(self):
        partial = "\n".join(self.block.splitlines()[:15]) + "\n"
        pull_request = PullRequest({"src/a.py": self.block, "src/b.py": partial})
        self.addCleanup(pull_request.close)
        self.assertIn("clean-code/duplication", rule_keys(pull_request.findings({"src/b.py": self.block})))

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
