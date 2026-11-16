import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("bundle", ROOT / "bundle.py")
BUNDLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUNDLE)


class BundlePolicyTests(unittest.TestCase):
    def pr(self, body="", labels=()):
        return {"body": body, "labels": [{"name": label} for label in labels],
                "user": {"login": "maintainer", "type": "User"}}

    def passes(self, pr, lines=0):
        return BUNDLE.decision(pr, "honua-io/example", lines)[0]

    def test_distinct_closing_references_include_lists_and_cross_repo(self):
        bodies = ["Closes #1, #2, #3", "Fixes #1\nResolves #2\nClosed #3",
                  "Closes #1 and honua-io/other#1, and #2",
                  "closes: #1, #2\nfix #3"]
        for body in bodies:
            with self.subTest(body=body):
                self.assertTrue(self.passes(self.pr(body)))

    def test_duplicates_mentions_and_examples_do_not_meet_the_rule(self):
        bodies = ["Closes #1, #1, honua-io/example#1", "See #1, #2, #3",
                  "Closes #1\n```md\nCloses #2, #3\n```",
                  "<!-- Closes #1, #2, #3 -->", "`Closes #1, #2, #3`",
                  "> Closes #1, #2, #3", "Closes #0, #1, #2", "Closes #1abc, #2abc, #3abc"]
        for body in bodies:
            with self.subTest(body=body):
                self.assertFalse(self.passes(self.pr(body)))

    def test_line_count_boundary(self):
        self.assertFalse(self.passes(self.pr(), 299))
        self.assertTrue(self.passes(self.pr(), 300))

    def test_exception_requires_label_category_and_reason(self):
        valid = "Lane: s-ci-gate\nBundle-exception: blocking red — restore required CI"
        self.assertTrue(self.passes(self.pr(valid, ["bundle-exception"])))
        for body in ("", "Bundle-exception: ", "Bundle-exception: blocking red",
                     "Bundle-exception: convenience — small patch",
                     "Bundle-exception:\nblocking red — repair",
                     "<!-- Bundle-exception: trunk-red — repair -->"):
            with self.subTest(body=body):
                self.assertFalse(self.passes(self.pr(body, ["bundle-exception"])))
        self.assertFalse(self.passes(self.pr(valid)))

    def test_all_bot_authors_are_exempt_but_bot_looking_users_are_not(self):
        for login in ("release-please[bot]", "dependabot[bot]", "automation[bot]"):
            pr = self.pr()
            pr["user"] = {"login": login, "type": "Bot"}
            self.assertTrue(self.passes(pr))
            pr["user"]["type"] = "User"
            self.assertFalse(self.passes(pr))

    def test_failure_names_the_rule(self):
        passed, reason = BUNDLE.decision(self.pr(), "honua-io/example", 1)
        self.assertFalse(passed)
        self.assertIn("Bundle rule:", reason)
        self.assertIn("300", reason)

    def test_summary_counts_lanes_and_reports_unattributed_and_invalid(self):
        items = [self.pr("Lane: s-ci-gate\nBundle-exception: trunk-red — repair",
                         ["bundle-exception"]),
                 self.pr("Lane: s-ci-gate", ["bundle-exception"]),
                 self.pr("", ["bundle-exception"])]
        text = BUNDLE.summary_text(items, "2026-11-09")
        self.assertIn("| s-ci-gate | 2 |", text)
        self.assertIn("unattributed", text)
        self.assertIn("missing valid reason: 2", text)

    def test_summary_paginates_and_fails_closed_on_incomplete_search(self):
        pages = [{"total_count": 2, "items": [{"number": 1}]},
                 {"total_count": 2, "items": [{"number": 2}]}]
        with patch.object(BUNDLE, "search_page", side_effect=pages) as search:
            self.assertEqual(len(BUNDLE.weekly_exceptions("2026-11-09")), 2)
            self.assertEqual(search.call_count, 2)
        for result in ({"total_count": 1001}, {"incomplete_results": True},
                       {"total_count": 1, "items": []}):
            with self.subTest(result=result):
                with patch.object(BUNDLE, "search_page", return_value=result):
                    with self.assertRaises(ValueError):
                        BUNDLE.weekly_exceptions("2026-11-09")


class BundleGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("commit", "--allow-empty", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True).strip()

    def test_numstat_counts_additions_deletions_and_binary_without_path_confusion(self):
        (self.repo / "old.txt").write_text("old\n" * 150)
        self.git("add", ".")
        self.git("commit", "-qm", "before")
        base = self.git("rev-parse", "HEAD")
        (self.repo / "old.txt").unlink()
        (self.repo / "new\tfile\n.txt").write_text("new\n" * 150)
        (self.repo / "binary").write_bytes(b"\0binary")
        self.git("add", ".")
        self.git("commit", "-qm", "candidate")
        args = argparse.Namespace(repo=self.repo, base=base, head="HEAD")
        self.assertEqual(BUNDLE.line_count(args), 300)

    def test_cli_fails_closed_with_missing_event(self):
        event = self.repo / "event.json"
        event.write_text(json.dumps({"repository": {"full_name": "honua-io/example"},
                                    "pull_request": {"body": "", "user": {"type": "User"}}}))
        command = ["python3", "-I", str(ROOT / "bundle.py"), "check", "--repo", str(self.repo),
                   "--base", self.base, "--head", "HEAD", "--event", str(event)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Bundle rule:", result.stdout)
        event.write_text("{}")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not evaluate", result.stderr)


class WorkflowContractTests(unittest.TestCase):
    def test_bundle_remains_in_the_existing_required_job(self):
        workflow = (ROOT.parent / ".github/workflows/repo-hygiene.yml").read_text()
        self.assertEqual(workflow.count("    name: Repository hygiene"), 1)
        self.assertIn("repo-hygiene/bundle.py check", workflow)
        self.assertIn('--base FETCH_HEAD^1 --head FETCH_HEAD --event "$GITHUB_EVENT_PATH"', workflow)
        self.assertNotIn("continue-on-error", workflow)

    def test_weekly_summary_has_read_only_app_access(self):
        workflow = (ROOT.parent / ".github/workflows/repo-hygiene-weekly.yml").read_text()
        self.assertIn("permission-pull-requests: read", workflow)
        self.assertIn('tee -a "$GITHUB_STEP_SUMMARY"', workflow)
        self.assertIn("set -o pipefail", workflow)


if __name__ == "__main__":
    unittest.main()
