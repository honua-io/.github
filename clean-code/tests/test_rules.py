import unittest
from pathlib import Path

from clean_code.check import run_checks
from clean_code.context import CheckContext, CheckOptions, XmlDocPolicy
from clean_code.git import Revisions
from tests.repo import ScratchRepository

FIXTURES = Path(__file__).parent / "fixtures" / "rules"
RULE_PREFIXES = ("clean-code/", "ruff/", "eslint/", "eslint/sonarjs/")


class PullRequest:
    """A scratch repository whose head commit is the change under check."""

    def __init__(self, base_files: dict[str, str]):
        self.scratch = ScratchRepository()
        self.base = self.scratch.commit(base_files)

    def findings(self, head_files: dict[str, str], options: CheckOptions = CheckOptions()) -> list:
        self.scratch.reset(self.base)
        head = self.scratch.commit(head_files)
        return run_checks(CheckContext(self.scratch.repository, Revisions(self.base, head), options))

    def close(self) -> None:
        self.scratch.close()


def rule_keys(findings: list) -> set[str]:
    return {finding.rule.key for finding in findings}


def fixture_rule_key(rule_directory: Path, known_keys: set[str]) -> str:
    return next(prefix + rule_directory.name for prefix in RULE_PREFIXES if prefix + rule_directory.name in known_keys)


class RuleFixtures(unittest.TestCase):
    """Each fixtures/rules/<rule>/ holds bad.* files that must trigger the rule and good.* files that must not."""

    def setUp(self):
        self.pull_request = PullRequest({"README.md": "fixture\n"})
        self.addCleanup(self.pull_request.close)

    def test_each_fixture_triggers_only_when_bad(self):
        from clean_code.catalog import RULES

        for rule_directory in sorted(FIXTURES.iterdir()):
            key = fixture_rule_key(rule_directory, set(RULES))
            for fixture in sorted(rule_directory.iterdir()):
                with self.subTest(f"{rule_directory.name}/{fixture.name}"):
                    target = f"src/{rule_directory.name}/{fixture.name}"
                    found = rule_keys(self.pull_request.findings({target: fixture.read_text()}))
                    self.assertEqual(key in found, fixture.stem.startswith("bad"), found)


class LineScope(unittest.TestCase):
    def test_only_added_lines_are_judged(self):
        pull_request = PullRequest({"src/a.cs": "// Fixes #1234.\nint a = 1;\n"})
        self.addCleanup(pull_request.close)
        self.assertEqual(pull_request.findings({"src/a.cs": "// Fixes #1234.\nint a = 2;\n"}), [])

    def test_line_separators_inside_source_cannot_fake_diff_headers(self):
        filler = "".join(f"int v{index} = {index};\n" for index in range(30))
        pull_request = PullRequest({"src/a.cs": "int a = 1;\n" + filler + "int z = 1;\n"})
        self.addCleanup(pull_request.close)
        fake_header = "var s = \"\u2028+++ b/zz.cs\";\n"
        head = "int a = 1;\n" + fake_header + filler + "int z = 1; // Fixes #1234.\n"
        found = pull_request.findings({"src/a.cs": head})
        self.assertIn(("src/a.cs", 33), {(f.location.path, f.location.line) for f in found})

    def test_generated_and_excluded_paths_are_skipped(self):
        pull_request = PullRequest({"README.md": "x\n"})
        self.addCleanup(pull_request.close)
        bad = "// Fixes #1234.\nint a = 1;\n"
        options = CheckOptions(excludes=("legacy/**",))
        found = pull_request.findings({"src/Migrations/M1.cs": bad, "legacy/old.cs": bad, "x.g.cs": bad}, options)
        self.assertEqual(found, [])


    def test_hashed_bundles_are_skipped_but_long_lines_are_not(self):
        pull_request = PullRequest({"README.md": "x\n"})
        self.addCleanup(pull_request.close)
        source = "// Fixes #1234.\n" + "var a=1;" * 200 + "\n"
        found = pull_request.findings({"site/assets/main-3f2aB9xQ.js": source, "src/config.js": source})
        self.assertEqual({finding.location.path for finding in found}, {"src/config.js"})

    def test_parameter_rules_skip_test_files(self):
        pull_request = PullRequest({"README.md": "x\n"})
        self.addCleanup(pull_request.close)
        theory = "class T\n{\n    void Case(int a, int b, int c, int d, bool expected) { }\n}\n"
        self.assertEqual(rule_keys(pull_request.findings({"tests/Api.Tests/CaseTests.cs": theory})), set())


class XmlDocPolicies(unittest.TestCase):
    def setUp(self):
        self.pull_request = PullRequest({"README.md": "x\n"})
        self.addCleanup(self.pull_request.close)

    def test_sdk_policy_allows_one_line_summary_only(self):
        source = "/// <summary>Parcel area.</summary>\npublic int Area { get; }\n/// <param name=\"x\">X.</param>\n/// <returns>Y.</returns>\npublic int F(int x) => x;\n"
        found = self.pull_request.findings({"src/Sdk.cs": source}, CheckOptions(xml_docs=XmlDocPolicy.PUBLIC_SUMMARY))
        self.assertEqual([finding.location.line for finding in found if finding.rule.key == "clean-code/xml-doc"], [3])


def numbered_lines(count: int, template: str) -> str:
    return "".join(template.format(index) + "\n" for index in range(count))


class SizesAndDuplication(unittest.TestCase):
    def setUp(self):
        self.existing = numbered_lines(801, "value_{0} = compute({0}, offset_{0})")
        self.pull_request = PullRequest({"src/big.py": self.existing})
        self.addCleanup(self.pull_request.close)

    def keys(self, head_files: dict[str, str]) -> set[str]:
        return rule_keys(self.pull_request.findings(head_files))

    def test_new_file_budget_is_inclusive(self):
        self.assertNotIn("clean-code/new-file-size", self.keys({"src/ok.py": numbered_lines(400, "a_{0} = {0}")}))
        self.assertIn("clean-code/new-file-size", self.keys({"src/new.py": numbered_lines(401, "b_{0} = {0}")}))

    def test_large_file_may_shrink_but_not_grow(self):
        self.assertIn("clean-code/large-file-growth", self.keys({"src/big.py": self.existing + "extra = 1\n"}))
        self.assertNotIn("clean-code/large-file-growth", self.keys({"src/big.py": self.existing[: -40]}))

    def test_copied_block_is_duplication_and_new_code_is_not(self):
        copied = "".join(self.existing.splitlines(keepends=True)[100:120])
        self.assertIn("clean-code/duplication", self.keys({"src/copy.py": copied}))
        self.assertNotIn("clean-code/duplication", self.keys({"src/fresh.py": numbered_lines(20, "fresh_{0} = make({0}, other_{0})")}))


def long_functions(body_lines: int) -> dict[str, str]:
    """One function per language spanning body_lines + 2 lines, plus a test file whose describe block is longer."""
    body = numbered_lines(body_lines, "    step_{0}()")
    statements = body.replace("()", "();")
    return {
        "src/long.py": "def long():\n" + body + "    return 1\n",
        "src/Long.cs": "class C\n{\n    void Long() {\n" + statements + "    }\n}\n",
        "src/long.ts": "export function long() {\n" + statements + "}\n",
        "src/spec/long.test.ts": "describe('x', () => {\n" + statements + "  it('t', () => {});\n});\n",
    }


class FunctionLength(unittest.TestCase):
    def setUp(self):
        self.pull_request = PullRequest({"README.md": "x\n"})
        self.addCleanup(self.pull_request.close)

    def flagged(self, sources: dict[str, str]) -> set[str]:
        found = self.pull_request.findings(sources)
        return {finding.location.path for finding in found if finding.rule.key == "clean-code/function-length"}

    def test_functions_over_budget_are_flagged_in_every_language(self):
        self.assertEqual(self.flagged(long_functions(59)), {"src/long.py", "src/Long.cs", "src/long.ts"})

    def test_functions_at_budget_and_test_blocks_pass(self):
        self.assertEqual(self.flagged(long_functions(58)), set())


if __name__ == "__main__":
    unittest.main()
