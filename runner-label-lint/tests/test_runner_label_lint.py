from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))

from lint_runner_labels import annotation, lint  # noqa: E402
from runner_labels.expressions import split_top_level, strip_parentheses  # noqa: E402
from runner_labels.policy import LabelPolicy  # noqa: E402
from runner_labels.runs_on import Finding  # noqa: E402

DEFAULT_LABELS = LabelPolicy()


def lint_fixture(case, labels=DEFAULT_LABELS):
    with tempfile.TemporaryDirectory() as repository:
        shutil.copytree(FIXTURES / case, Path(repository) / ".github" / "workflows")
        return lint(repository, labels)


class FixtureTests(unittest.TestCase):
    def assert_findings(self, case, expected_count, fragment=""):
        findings = lint_fixture(case)
        self.assertEqual(expected_count, len(findings), [str(finding) for finding in findings])
        for finding in findings:
            self.assertIn(fragment, str(finding))
        return findings

    def test_rejects_self_hosted_labels_for_pull_request_jobs(self):
        cases = {"literal-self-hosted": 1, "label-list": 1, "custom-label": 1, "pull-request-target": 1}
        for case, count in cases.items():
            with self.subTest(case=case):
                self.assert_findings(case, count, "is not a GitHub-hosted runner")

    def test_ignores_jobs_fork_events_cannot_reach(self):
        for case in ("push-only", "job-if-excludes-pull-request", "job-if-fork-guard"):
            with self.subTest(case=case):
                self.assert_findings(case, 0)

    def test_accepts_the_fork_guarded_expression_and_hosted_choices(self):
        for case in ("approved-guard", "hosted-conditional", "matrix-hosted"):
            with self.subTest(case=case):
                self.assert_findings(case, 0)

    def test_requires_the_workflow_run_guard_for_workflow_run_triggers(self):
        self.assert_findings("missing-workflow-run-guard", 1, "head_repository.full_name")

    def test_rejects_unguarded_or_misplaced_guards(self):
        for case in ("unguarded-variable", "guard-not-conjoined"):
            with self.subTest(case=case):
                self.assert_findings(case, 1, "without the fork guard")

    def test_requires_a_hosted_fallback(self):
        self.assert_findings("no-hosted-fallback", 1, "no GitHub-hosted fallback")

    def test_resolves_matrix_values(self):
        self.assert_findings("matrix-include-self-hosted", 1, "is not a GitHub-hosted runner")
        self.assert_findings("matrix-from-json", 1, "'matrix.runner'")

    def test_rejects_runner_groups_and_partial_templates(self):
        self.assert_findings("runner-group", 1, "runner group")
        self.assert_findings("partial-template", 1, "mixes literal text")

    def test_fails_closed_on_unreadable_workflows(self):
        self.assert_findings("invalid-yaml", 1, "cannot be checked")

    def test_follows_local_reusable_workflows(self):
        [finding] = self.assert_findings("reusable-self-hosted", 1, "label 'self-hosted'")
        self.assertEqual(".github/workflows/build.yml", finding.path)
        self.assertEqual(5, finding.line)

    def test_resolves_inputs_through_each_caller(self):
        [finding] = self.assert_findings("reusable-inputs", 1, "'vars.HEAVY'")
        self.assertEqual(".github/workflows/build.yml", finding.path)

    def test_reports_file_and_line(self):
        [finding] = self.assert_findings("literal-self-hosted", 1)
        self.assertTrue(str(finding).startswith(".github/workflows/ci.yml:5: jobs.build.runs-on:"))


class LabelPolicyTests(unittest.TestCase):
    def test_hosted_labels(self):
        for label in ("ubuntu-latest", "ubuntu-24.04", "ubuntu-24.04-arm", "ubuntu-slim", "windows-2025",
                      "windows-11-arm", "macos-15", "macos-latest-xlarge", "Ubuntu-Latest"):
            with self.subTest(label=label):
                self.assertTrue(DEFAULT_LABELS.is_hosted(label))

    def test_everything_else_is_denied(self):
        for label in ("self-hosted", "honua-light", "linux", "x64", "ubuntu-latest-custom", ""):
            with self.subTest(label=label):
                self.assertFalse(DEFAULT_LABELS.is_hosted(label))

    def test_allow_and_deny_lists(self):
        labels = LabelPolicy(allowed=frozenset({"org-large-4core"}), denied=frozenset({"ubuntu-22.04"}))
        self.assertTrue(labels.is_hosted("org-large-4core"))
        self.assertFalse(labels.is_hosted("ubuntu-22.04"))
        self.assertEqual(1, len(lint_fixture("custom-label", labels)))


class ExpressionTests(unittest.TestCase):
    def test_split_ignores_operators_in_strings_and_brackets(self):
        parts = split_top_level("a && 'x || y' || (b || c) || f('it''s || z')", "||")
        self.assertEqual(["a && 'x || y'", "(b || c)", "f('it''s || z')"], parts)

    def test_strip_parentheses_keeps_separate_groups(self):
        self.assertEqual("a || b", strip_parentheses("((a || b))"))
        self.assertEqual("(a) && (b)", strip_parentheses("(a) && (b)"))


class OutputTests(unittest.TestCase):
    def test_annotation_escapes_repository_text(self):
        finding = Finding(".github/workflows/a,b.yml", 3, "label 'x'\n::warning::y", "hint")
        line = annotation(finding)
        self.assertEqual(1, len(line.splitlines()))
        self.assertTrue(line.startswith("::error file=.github/workflows/a%2Cb.yml,line=3::"))

    def test_command_line_exit_codes(self):
        script = ROOT / "lint_runner_labels.py"
        for case, code in (("approved-guard", 0), ("literal-self-hosted", 1)):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as repository:
                shutil.copytree(FIXTURES / case, Path(repository) / ".github" / "workflows")
                result = subprocess.run([sys.executable, "-I", str(script), "--repo", repository],
                                        capture_output=True, text=True, check=False)
                self.assertEqual(code, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
