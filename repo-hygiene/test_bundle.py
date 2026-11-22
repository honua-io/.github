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
                  "> Closes #1, #2, #3", "    Closes #1, #2, #3",
                  "\tCloses #1, #2, #3", "```md\nCloses #1, #2, #3", "Closes #0, #1, #2", "Closes #1abc, #2abc, #3abc"]
        for body in bodies:
            with self.subTest(body=body):
                self.assertFalse(self.passes(self.pr(body)))

    def test_multiline_code_spans_are_examples(self):
        for delimiter in ("`", "``"):
            with self.subTest(delimiter=delimiter):
                body = f"{delimiter}Example:\nCloses #1, #2, #3\n{delimiter}"
                self.assertFalse(self.passes(self.pr(body)))
                body = f"{delimiter}Example:\nBundle-exception: trunk-red — example\n{delimiter}"
                self.assertFalse(self.passes(self.pr(body, ["bundle-exception"])))
        self.assertFalse(self.passes(self.pr("``single ` tick\nCloses #1, #2, #3\n``")))

    def test_issue_urls_count_and_deduplicate_with_shorthand(self):
        body = "Closes https://github.com/honua-io/example/issues/1, #2, honua-io/other#3"
        self.assertTrue(self.passes(self.pr(body)))
        body = "Closes https://github.com/honua-io/example/issues/1, #1, #2"
        self.assertFalse(self.passes(self.pr(body)))
        body = "\n".join(f"Fixes https://github.com/Honua-io/other/issues/{n}" for n in (1, 2, 3))
        self.assertTrue(self.passes(self.pr(body)))
        body = "Closes https://github.com/honua-io/example/issues/1abc, #2, #3"
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

    def test_standing_rule_single_and_two_ticket_exceptions(self):
        for category in ("single authorized by main standing rule",
                         "single authorized by main standing rule (21 Nov 15:40 HST)",
                         "two-ticket bundle authorized by main standing rule"):
            body = f"Bundle-exception: {category} — no third small ticket to bundle"
            with self.subTest(category=category):
                self.assertTrue(self.passes(self.pr(body, ["bundle-exception"])))
                self.assertFalse(self.passes(self.pr(body)))
        for body in ("Bundle-exception: single authorized by main standing rule",
                     "Bundle-exception: single authorized by main standing rule (21 Nov)",
                     "Bundle-exception: two-ticket authorized by main standing rule — x",
                     "Bundle-exception: authorized by main standing rule — small patch",
                     "Bundle-exception: single authorized by main — small patch",
                     "single authorized by main standing rule — no label line"):
            with self.subTest(body=body):
                self.assertFalse(self.passes(self.pr(body, ["bundle-exception"])))

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

    def test_unchanged_and_modified_renames_count_only_changed_lines(self):
        old = self.repo / "old\tfile\n.txt"
        old.write_text("same\n" * 150)
        self.git("add", ".")
        self.git("commit", "-qm", "before")
        base = self.git("rev-parse", "HEAD")
        renamed = self.repo / "new\tfile\n.txt"
        old.rename(renamed)
        self.git("add", ".")
        self.git("commit", "-qm", "rename")
        args = argparse.Namespace(repo=self.repo, base=base, head="HEAD")
        self.assertEqual(BUNDLE.line_count(args), 0)
        renamed.write_text(renamed.read_text() + "changed\n")
        self.git("add", ".")
        self.git("commit", "-qm", "edit")
        self.assertEqual(BUNDLE.line_count(args), 1)

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
        self.assertIn("run: node repo-hygiene/app-coverage.cjs", workflow)
        self.assertLess(workflow.index("run: node repo-hygiene/app-coverage.cjs"),
                        workflow.index("repo-hygiene/bundle.py summary"))

    def test_report_rejects_partial_suspended_or_wrong_organization_installations(self):
        script = r"""
const {requireOrganizationCoverage} = require('./repo-hygiene/app-coverage.cjs');
const assert = require('node:assert/strict');
const valid = {account: {login: 'honua-io', type: 'Organization'}, repository_selection: 'all'};
assert.doesNotThrow(() => requireOrganizationCoverage(valid));
for (const invalid of [{...valid, repository_selection: 'selected'},
  {...valid, suspended_at: '2026-11-16'},
  {...valid, account: {login: 'other', type: 'Organization'}},
  {...valid, account: {login: 'honua-io', type: 'User'}}, {}]) {
  assert.throws(() => requireOrganizationCoverage(invalid));
}
"""
        subprocess.run(["node", "-e", script], cwd=ROOT.parent, check=True)

    def test_report_verifies_installation_with_read_only_authenticated_request(self):
        script = r"""
const assert = require('node:assert/strict');
const {generateKeyPairSync} = require('node:crypto');
const {checkCoverage} = require('./repo-hygiene/app-coverage.cjs');
const {privateKey} = generateKeyPairSync('rsa', {modulusLength: 2048});
process.env.BOT_APP_PRIVATE_KEY = privateKey.export({type: 'pkcs8', format: 'pem'});
process.env.BOT_APP_ID = '123';
process.env.INSTALLATION_ID = '456';
global.fetch = async (url, options) => {
  assert.equal(url, 'https://api.github.com/app/installations/456');
  assert.equal(options.method, undefined);
  assert.match(options.headers.Authorization, /^Bearer [^.]+\.[^.]+\.[^.]+$/);
  return {ok: true, json: async () => ({account: {login: 'honua-io', type: 'Organization'},
    repository_selection: 'all'})};
};
(async () => {
  await checkCoverage();
  global.fetch = async () => ({ok: false});
  await assert.rejects(checkCoverage());
  global.fetch = async () => {throw new Error('network unavailable')};
  await assert.rejects(checkCoverage());
})().catch(() => {process.exitCode = 1});
"""
        subprocess.run(["node", "-e", script], cwd=ROOT.parent, check=True)


if __name__ == "__main__":
    unittest.main()
