import re
import tomllib
import unittest
from pathlib import Path

from clean_code.catalog import RULES, markdown_table
from clean_code.findings import Finding, Location
from clean_code.comment_only import Verdict
from clean_code.report import Report, declarations, quality_exceptions

TOOL_DIRECTORY = Path(__file__).resolve().parents[1]
BLOCKING = Finding.of("clean-code/ticket-reference", Location("src/a.cs", 3), "'#12': move it")
ADVISORY = Finding.of("ruff/PLR2004", Location("src/b.py", 9), "Magic value used in comparison")


class QualityException(unittest.TestCase):
    def test_reasons_are_read_from_the_pr_body(self):
        body = "Summary\n\nquality-exception: generated client, regenerated not edited\n"
        self.assertEqual(quality_exceptions(body), ["generated client, regenerated not edited"])

    def test_a_bare_marker_without_reason_is_not_an_exception(self):
        self.assertEqual(quality_exceptions("quality-exception:\n"), [])

    def test_blocking_findings_fail_without_an_exception(self):
        report = Report([BLOCKING, ADVISORY], [])
        self.assertFalse(report.passed)
        self.assertEqual([line.split(" ")[0] for line in report.annotations()], ["::error", "::notice"])

    def test_an_exception_passes_but_is_logged(self):
        report = Report([BLOCKING], ["vendored file"])
        self.assertTrue(report.passed)
        self.assertTrue(report.annotations()[0].startswith("::warning"))
        self.assertIn("**quality-exception:** vendored file", report.summary())

    def test_annotations_carry_the_smell_code(self):
        self.assertIn("title=C1 Ticket or PR reference in a comment::", Report([BLOCKING], []).annotations()[0])


class Declarations(unittest.TestCase):
    def test_declarations_count_only_on_their_own_line(self):
        body = "This PR is a `clean-code: comment-only` cleanup.\nclean-code: docstring-removal\n"
        self.assertEqual(declarations(body), {"docstring-removal"})

    def test_a_disproved_comment_only_claim_fails_even_under_an_exception(self):
        report = Report([], ["bulk cleanup"], comment_only_verdicts=[Verdict("a.cs", "code differs")])
        self.assertFalse(report.passed)
        self.assertIn("**not proven** for 1 files", report.summary())


class CatalogConsistency(unittest.TestCase):
    def test_readme_table_matches_the_catalog(self):
        self.assertIn(markdown_table(), (TOOL_DIRECTORY / "README.md").read_text())

    def test_every_eslint_rule_is_catalogued(self):
        config = (TOOL_DIRECTORY / "eslint.config.mjs").read_text()
        enabled = set(re.findall(r'"([\w/-]+)": \[?"(?:error|warn)"', config)) | set(re.findall(r'\b(complexity): \[', config))
        self.assertEqual({f"eslint/{rule}" for rule in enabled} - set(RULES), set())

    def test_every_ruff_selection_is_catalogued(self):
        selected = tomllib.loads((TOOL_DIRECTORY / "ruff.toml").read_text())["lint"]["select"]
        ruff_keys = [key for key in RULES if key.startswith("ruff/")]
        uncovered = [code for code in selected if not any(key.startswith(f"ruff/{code}") for key in ruff_keys)]
        self.assertEqual(uncovered, [])


if __name__ == "__main__":
    unittest.main()
