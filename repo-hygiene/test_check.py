import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("hygiene", ROOT / "check.py")
RULES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RULES)


class PathPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = {"roots": ["src/", "tests/", "docs/", "eng/", "artifacts/", "README.md"],
                      "gate_inputs": {"eng/release/audit.v1.json": "Release gate input"}}
        cls.rules = RULES

    def test_rejects_scratch_history_outputs_and_unexpected_roots(self):
        paths = [".flow/pr-body.md", "src/tmp/note.txt", "docs/scratch/plan.md",
                 "eng/wip/probe.py", "docs/audits/check.md", "docs/archive/old.md",
                 "docs/reports/result.md", "eng/evidence/result.json", "src/fix.orig",
                 "src/fix.rej", "src/fix.bak", "docs/run-2026-11-06.md",
                 "eng/20261106/input.json", "docs/preview-2026-05.md",
                 "samples/demo.py", "surprise.py", "docs/test-report.json",
                 "src/TMP/readme.md", "docs/scratch-test/probe.md", "src/.tmp/readme.md",
                 "docs/evidence-rc/result.json", "docs/.archive/old.md",
                 "docs/.evidence/results.json", "docs/notes/2026.11.06.md",
                 "docs/2026.11.06/note.md", "src/service.cs~", "src/.service.cs.swp",
                 "src/service.cs.backup", "src/service.cs.bak.1", "src/service.cs.~1~",
                 "artifacts/run-2026-11-06/report.json"]
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(self.rules.violation(path, self.policy))

    def test_accepts_live_code_docs_tooling_outputs_and_exact_gate_inputs(self):
        for path in ("src/reports.py", "tests/test_evidence.py", "docs/guides/deploy.md",
                     "README.md", "eng/matrix.v1.json", "src/backup.py", "src/Swap.cs",
                     "eng/release/audit.v1.json"):
            with self.subTest(path=path):
                self.assertIsNone(self.rules.violation(path, self.policy))
        self.assertTrue(self.rules.violation("eng/release/audit.v2.json", self.policy))

    def test_sample_repository_can_keep_its_product(self):
        policy = {"roots": ["samples/"], "gate_inputs": {}, "samples": True}
        self.assertIsNone(self.rules.violation("samples/demo/main.py", policy))

    def test_directory_gate_inputs_are_scoped_to_literal_prefixes(self):
        policy = {"roots": ["samples/", "mcp/"],
                  "gate_input_directories": {"samples/evidence/": "Release seal input",
                                             "mcp/evals/runs/": "Release scorecard input"}}
        for path in ("samples/evidence/run-2026-11-06/receipt.json",
                     "samples/evidence/demo/runs/new-id/artifacts/receipt.json",
                     "mcp/evals/runs/new-id/report.json"):
            with self.subTest(path=path):
                self.assertIsNone(self.rules.violation(path, policy))
        for path in ("samples/evidence-other/report.json", "samples/evidence.json",
                     "samples/demo/main.py", "mcp/evals/runs-other/report.json",
                     "samples/evidence/tmp/probe.json", "samples/evidence/report.json.bak",
                     "samples/evidence/demo/artifacts/tmp/probe.json",
                     "samples/evidence/demo/artifacts/receipt.json.bak",
                     "samples/evidence/demo/test-results/receipt.json"):
            with self.subTest(path=path):
                self.assertTrue(self.rules.violation(path, policy))

    def test_artifacts_are_reserved_outside_explicit_gate_input_directories(self):
        policy = {"roots": ["artifacts/", "samples/", "mcp/", "docs/"],
                  "gate_input_directories": {"samples/evidence/": "Release seal input"}}
        for path in ("artifacts/receipt.json", "samples/artifacts/receipt.json",
                     "samples/evidence-other/artifacts/receipt.json",
                     "mcp/evals/runs/new-id/artifacts/receipt.json", "docs/artifacts/guide.md"):
            with self.subTest(path=path):
                self.assertEqual(self.rules.violation(path, policy),
                                 "run output must stay untracked under ignored artifacts/")

    def test_maintained_automation_is_not_run_output(self):
        policy = {"roots": [".github/"], "gate_inputs": {}}
        for path in (".github/workflows/notify-evidence.yml", ".github/ISSUE_TEMPLATE/bug_report.yml",
                     ".github/actions/upload-evidence/action.yml"):
            with self.subTest(path=path):
                self.assertIsNone(self.rules.violation(path, policy))
        self.assertTrue(self.rules.violation(".github/workflows/evidence/run.json", policy))
        output = ".github/workflows/audit-2026-11-06.md"
        self.assertEqual(self.rules.violation(output, policy), "date-stamped output belongs under ignored artifacts/")
        policy["gate_inputs"][output] = "Pinned contract required by the release checker"
        self.assertIsNone(self.rules.violation(output, policy))

    def test_source_modules_are_maintained_but_data_snapshots_need_exact_exceptions(self):
        for path in ("src/reports/Report.cs", "src/archive/Archive.cs", "tests/snapshots/test_report.py",
                     "src/migrations/V2026_11_06__init.sql", "src/Coverage/CoverageService.cs",
                     "src/Results/Result.cs", "tests/Results/ResultsTests.cs"):
            with self.subTest(path=path):
                self.assertIsNone(self.rules.violation(path, self.policy))
        self.assertEqual(self.rules.violation("tests/snapshots/results.json", self.policy),
                         "historical output belongs under ignored artifacts/")

    def test_live_prose_is_distinct_from_named_run_reports(self):
        for path in ("docs/security/audit-logging.md", "docs/guides/reports.md", "docs/admin/snapshots.md",
                     "docs/guides/reports.html"):
            with self.subTest(path=path):
                self.assertIsNone(self.rules.violation(path, self.policy))
        for path in ("docs/test-report.json", "docs/release-audit.md", "docs/report.md",
                     "docs/coverage-report.html", "docs/observations.md", "docs/observation.md"):
            with self.subTest(path=path):
                self.assertEqual(self.rules.violation(path, self.policy),
                                 "run output requires an exact gate-input exception")

    def test_pinned_live_pages_and_workflow_templates_remain_product_files(self):
        policy = {"roots": ["evidence-demo.html", "workflow-templates/"], "gate_inputs": {}}
        self.assertIsNone(self.rules.violation("evidence-demo.html", policy))
        self.assertIsNone(self.rules.violation("workflow-templates/dependency-audit.yml", policy))

    def test_output_roots_and_scratch_files_are_rejected_for_their_actual_reason(self):
        for path in ("artifacts/report.json", "src/coverage/home.png", "tests/test-results/home.png"):
            self.assertEqual(self.rules.violation(path, self.policy),
                             "run output must stay untracked under ignored artifacts/")
        for path in ("src/scratch.md", "docs/wip.md", "docs/tmp/notes.md"):
            self.assertEqual(self.rules.violation(path, self.policy),
                             "scratch belongs outside tracked product files")


class BackendParsingTests(unittest.TestCase):
    def test_comments_strings_and_heredocs_do_not_create_blocks(self):
        text = ('# backend "s3" {}\n/* backend "s3" {} */\n'
                'value = "backend \"s3\" {}"\n'
                'script = <<-EOF\nbackend "s3" {}\nEOF\n')
        self.assertEqual(RULES.backend_blocks(text), [])

    def test_braces_in_strings_do_not_end_a_block(self):
        text = 'terraform { backend "s3" { key = "}" options = { region = "eu" } } }'
        self.assertEqual(len(RULES.backend_blocks(text)), 1)
        self.assertIn('"}"', RULES.backend_blocks(text)[0])

    def test_unquoted_backend_labels_are_protected(self):
        blocks = RULES.backend_blocks('terraform { backend s3 { bucket = "state" } }')
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0][1], 's3')

    def test_unterminated_backend_fails_closed(self):
        with self.assertRaises(ValueError):
            RULES.backend_blocks('terraform { backend "s3" {')


class GitDiffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.git("init", "-b", "main")
        self.write("docs/archive/old.md", "old\n")
        self.write("README.md", "hello\n")
        self.write(RULES.POLICY_PATH, json.dumps({"roots": [".github/", "docs/", "README.md"]}))
        self.base = self.commit()

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *arguments):
        return subprocess.check_output(["git", "-C", str(self.repo), *arguments],
                                       stderr=subprocess.DEVNULL, text=True).strip()

    def write(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def commit(self, message="fixture"):
        self.git("add", ".")
        self.git("-c", "user.name=Mike McDougall", "-c", "user.email=mike@honua.io",
                 "commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def check(self, head="HEAD", event=None):
        return subprocess.run(["python3", "-I", str(ROOT / "check.py"), "--repo", str(self.repo),
                               "--base", self.base, "--head", head] +
                              (["--event", str(event)] if event else []),
                              capture_output=True, text=True)

    def test_owned_file_changes_and_deletions_are_rejected(self):
        paths = ["llms.txt", "docs/llms-full.txt", "CHANGELOG.md", "samples/dist/app.js",
                 "docs/bundle-sizes.md", "api-report/client.api.md"]
        for path in paths:
            self.write(path, "original\n")
        self.base = self.commit()
        for path in paths:
            self.write(path, "modified\n")
        self.commit()
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stdout.count("derived file is owned"), len(paths))
        for path in paths:
            (self.repo / path).unlink()
        self.commit()
        self.assertEqual(self.check().stdout.count("derived file is owned"), len(paths))

    def release_fixture(self, extra_paths=(), new_paths=(),
                        branch="release-please--branches--main--components--sdk", subject="fixture", contents=None,
                        changelogs=("CHANGELOG.md", "docs/CHANGELOG.md")):
        for path in changelogs:
            self.write(path, "original\n")
        for path in extra_paths:
            self.write(path, "original\n")
        self.base = self.commit()
        self.git("switch", "-c", branch)
        for path in (*changelogs, *extra_paths, *new_paths):
            self.write(path, (contents or {}).get(path, "release update\n"))
        candidate = self.commit(subject)
        self.git("switch", "main")
        self.write("README.md", "advanced base\n")
        self.base = self.commit()
        self.git("-c", "user.name=Mike McDougall", "-c", "user.email=mike@honua.io",
                 "merge", "--no-ff", "--no-edit", branch)
        identity = {"login": "honua-io-bot[bot]", "id": 321210756, "type": "Bot"}
        repository = {"full_name": "honua-io/example"}
        return {"repository": repository, "sender": dict(identity), "pull_request": {
            "user": dict(identity), "base": {"repo": repository, "ref": "main"},
            "head": {"repo": repository, "ref": branch, "sha": candidate}}}

    def check_event(self, event):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text(json.dumps(event))
            return self.check(event=path)

    def test_release_bots_can_update_changelogs_in_the_fetched_merge(self):
        event = self.release_fixture()
        for login, user_id in (("honua-io-bot[bot]", 321210756), ("github-actions[bot]", 41898282)):
            with self.subTest(login=login):
                identity = {"login": login, "id": user_id, "type": "Bot"}
                event["sender"] = event["pull_request"]["user"] = identity
                result = self.check_event(event)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.check().returncode, 1)

    def test_release_exception_rejects_untrusted_or_mismatched_events(self):
        event = self.release_fixture()
        changes = [
            (("pull_request", "user", "login"), "lookalike[bot]"),
            (("pull_request", "user", "id"), 1),
            (("pull_request", "user", "type"), "User"),
            (("sender", "id"), 1),
            (("sender", "type"), "User"),
            (("pull_request", "head", "repo", "full_name"), "fork/example"),
            (("pull_request", "base", "repo", "full_name"), "other/example"),
            (("repository", "full_name"), "other/example"),
            (("pull_request", "head", "sha"), self.base),
            (("pull_request", "head", "ref"), "release-please--branches--other"),
            (("pull_request", "head", "ref"), "release-please--branches--main-pretend"),
            (("pull_request", "head", "ref"), "release-please--branches--main--components--"),
            (("pull_request", "base", "ref"), "other"),
        ]
        for keys, value in changes:
            with self.subTest(keys=keys, value=value):
                altered = json.loads(json.dumps(event))
                target = altered
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                result = self.check_event(altered)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(result.stdout.count("derived file is owned"), 2)
        for incomplete in ({}, {"pull_request": {}}):
            self.assertEqual(self.check_event(incomplete).returncode, 1)
        # A non-merge commit cannot acquire the exemption using copied event metadata.
        self.git("checkout", "--detach", event["pull_request"]["head"]["sha"])
        self.assertEqual(self.check_event(event).returncode, 1)

    def test_release_exception_keeps_other_ownership_and_path_checks(self):
        event = self.release_fixture(("docs/llms-full.txt", "docs/bundle-sizes.md",
                                      "samples/dist/CHANGELOG.md", "api-report/CHANGELOG.md"),
                                     ("docs/archive/CHANGELOG.md",))
        result = self.check_event(event)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(result.stdout.count("derived file is owned"), 4)
        self.assertNotIn('"CHANGELOG.md":', result.stdout)
        self.assertNotIn('"docs/CHANGELOG.md":', result.stdout)
        self.assertIn('"docs/archive/CHANGELOG.md": historical output belongs under ignored artifacts/',
                      result.stdout)

    def derived_fixture(self, extra_paths=(), new_paths=(), subject=None,
                        changelogs=("CHANGELOG.md", "docs/CHANGELOG.md")):
        return self.release_fixture(
            ("llms-full.txt", "api-report/stable-api.json", "docs/bundle-sizes.md",
             "samples/dist/capability-sample-matrix.v2.json", *extra_paths), new_paths,
            branch="automation/derived-artifacts-43832728979-1",
            subject=subject or "chore(evidence): regenerate derived artifacts (evidence) for abc1234",
            contents={"docs/state.tf": 'terraform { backend "s3" {} }\n'}, changelogs=changelogs)

    def test_trusted_generated_only_update_passes(self):
        event = self.derived_fixture(changelogs=())
        result = self.check_event(event)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_trusted_regeneration_can_update_generated_files_but_not_changelogs(self):
        event = self.derived_fixture()
        result = self.check_event(event)
        self.assertEqual(result.stdout.count("derived file is owned"), 2, result.stdout)
        self.assertIn('"CHANGELOG.md":', result.stdout)
        self.assertIn('"docs/CHANGELOG.md":', result.stdout)
        self.assertNotIn('"llms-full.txt":', result.stdout)
        self.assertEqual(self.check().stdout.count("derived file is owned"), 6)

    def test_regeneration_rejects_untrusted_events_and_invalid_branch(self):
        event = self.derived_fixture()
        changes = [
            (("pull_request", "user", "id"), 1),
            (("pull_request", "user", "type"), "User"),
            (("sender", "id"), 1),
            (("pull_request", "head", "repo", "full_name"), "fork/example"),
            (("pull_request", "head", "sha"), self.base),
            (("pull_request", "head", "ref"), "automation/derived-artifacts-1-1-extra"),
            (("pull_request", "head", "ref"), "automation/derived-artifacts-0-1"),
        ]
        for keys, value in changes:
            with self.subTest(keys=keys):
                altered = json.loads(json.dumps(event))
                target = altered
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                self.assertEqual(self.check_event(altered).stdout.count("derived file is owned"), 6)
        self.git("checkout", "--detach", event["pull_request"]["head"]["sha"])
        self.assertEqual(self.check_event(event).stdout.count("derived file is owned"), 6)

    def test_regeneration_requires_publisher_commit_marker(self):
        event = self.derived_fixture(subject="ordinary change")
        self.assertEqual(self.check_event(event).stdout.count("derived file is owned"), 6)

    def test_regeneration_preserves_added_path_and_backend_rules(self):
        event = self.derived_fixture(new_paths=("docs/archive/new.md", "docs/state.tf"))
        # The ordinary added-path check applies even with a trusted publisher event.
        result = self.check_event(event)
        self.assertIn("historical output belongs", result.stdout)
        self.assertIn("backend blocks may not change", result.stdout)

    def test_terraform_resource_changes_and_backend_formatting_are_allowed(self):
        self.write("docs/state.tf", 'terraform { backend "s3" { bucket = "state" } }\nresource "x" "y" {}\n')
        self.base = self.commit()
        self.write("docs/state.tf", 'terraform { backend "s3" { # state location\n bucket="state" } }\nresource "x" "z" {}\n')
        self.commit()
        self.assertEqual(self.check().returncode, 0, self.check().stdout)

    def test_terraform_backend_changes_and_deletions_are_rejected(self):
        self.write("docs/state.tf", 'terraform { backend "s3" { bucket = "state" } }\n')
        self.base = self.commit()
        self.write("docs/state.tf", 'terraform { backend "s3" { bucket = "other" } }\n')
        self.commit()
        self.assertIn("backend blocks may not change", self.check().stdout)
        (self.repo / "docs/state.tf").unlink()
        self.commit()
        self.assertIn("backend blocks may not change", self.check().stdout)

    def test_backend_additions_are_rejected_without_a_prior_file(self):
        self.write("docs/new.tf", 'terraform { backend "s3" {} }\n')
        self.commit()
        self.assertIn("backend blocks may not change", self.check().stdout)

    def test_existing_history_modifications_and_deletions_are_allowed(self):
        self.write("docs/archive/old.md", "updated\n")
        self.commit()
        self.assertEqual(self.check().returncode, 0)
        (self.repo / "docs/archive/old.md").unlink()
        self.commit()
        self.assertEqual(self.check().returncode, 0)

    def test_rename_destination_is_added_history(self):
        self.git("mv", "README.md", "docs/archive/new.md")
        self.commit()
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn('"docs/archive/new.md": historical output', result.stdout)

    def test_candidate_cannot_substitute_its_own_policy(self):
        replacement = {"roots": [".github/", "surprise.py"]}
        self.write(RULES.POLICY_PATH, json.dumps(replacement))
        self.write("surprise.py", "candidate code\n")
        self.assertIsNone(RULES.violation("surprise.py", replacement))
        self.commit()
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn('"surprise.py": unexpected top-level entry', result.stdout)

    def test_path_boundaries_newlines_and_unicode_are_read_as_git_paths(self):
        for name in ("docs/receipts/check.json", "docs/audit\nreport.md", "docs/20261106/地図.md"):
            self.write(name, "result\n")
        self.commit()
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("3 violation(s)", result.stdout)

    def test_missing_revision_or_base_policy_fails_closed(self):
        self.assertEqual(self.check(head="missing").returncode, 1)
        self.git("rm", RULES.POLICY_PATH)
        self.base = self.commit()
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not evaluate", result.stdout)

    def test_malformed_base_policy_fails_closed(self):
        invalid = [[], {}, {"roots": ["docs/nested/"]}, {"roots": ["../"]},
                   {"roots": [None]}, {"roots": ["docs/"], "gate_inputs": []},
                   {"roots": ["docs/"], "gate_inputs": {"docs/audit.json": ""}},
                   {"roots": ["docs/"], "gate_inputs": {"outside.json": "Gate"}},
                   {"roots": ["docs/"], "gate_inputs": {"docs/artifacts/input.json": "Gate"},
                    "gate_input_directories": None},
                   {"roots": ["docs/"], "gate_inputs": {"docs/artifacts/input.json": "Gate"},
                    "gate_input_directories": 1},
                   {"roots": ["docs/"], "samples": "false"}]
        for policy in invalid:
            with self.subTest(policy=policy):
                self.write(RULES.POLICY_PATH, json.dumps(policy))
                self.base = self.commit()
                result = self.check()
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("could not evaluate", result.stdout)

    def test_directory_gate_inputs_are_validated_and_read_from_base(self):
        policy = {"roots": [".github/", "samples/"],
                  "gate_input_directories": {"samples/evidence/": "Release seal input"}}
        self.write(RULES.POLICY_PATH, json.dumps(policy))
        self.base = self.commit()
        self.write("samples/evidence/new-run/receipt-2026-11-06.json", "gate input\n")
        self.write("samples/evidence/new-run/artifacts/seal-input.json", "bound gate input\n")
        self.commit()
        self.assertEqual(self.check().returncode, 0)
        policy["gate_input_directories"]["samples/demo/"] = "Candidate-only exception"
        self.write(RULES.POLICY_PATH, json.dumps(policy))
        self.write("samples/demo/main.py", "candidate code\n")
        self.commit()
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('"samples/demo/main.py": product demonstrations', result.stdout)

    def test_exact_gate_input_rules_remain_unchanged(self):
        policy = {"roots": [".github/", "docs/", "samples/"],
                  "gate_inputs": {"docs/[id].json": "Literal gate input",
                                  "docs/{input}.json": "Literal gate input",
                                  "docs/a\\b.json": "Literal gate input"}}
        self.write(RULES.POLICY_PATH, json.dumps(policy))
        self.base = self.commit()
        loaded = RULES.load_policy(self.repo, self.base)
        for path in policy["gate_inputs"]:
            self.assertIsNone(RULES.violation(path, loaded))
        policy["gate_inputs"]["samples/demo.py"] = "Cannot bypass product sample ban"
        self.write(RULES.POLICY_PATH, json.dumps(policy))
        self.base = self.commit()
        with self.assertRaisesRegex(ValueError, "cannot override forbidden paths"):
            RULES.load_policy(self.repo, self.base)

    def test_malformed_directory_exceptions_fail_closed(self):
        invalid = [[], {"docs/evidence/": ""}, {"docs/evidence": "Input"},
                   {"docs/*/": "Input"}, {"docs/evidence?/": "Input"},
                   {"docs/[evidence]/": "Input"}, {"docs/{evidence}/": "Input"},
                   {"docs/../evidence/": "Input"}, {"outside/evidence/": "Input"},
                   {"docs/artifacts/": "Input"}, {"artifacts/": "Input"},
                   {"docs/a/": "Input", "docs/a/artifacts/": "Input"},
                   {"docs/a/": "Input", "docs/a/Artifacts/": "Input"},
                   {"docs/tmp/": "Input"},
                   {"docs/fix.bak/": "Input"}, {"docs/evidence//": "Input"}]
        for exceptions in invalid:
            with self.subTest(exceptions=exceptions):
                policy = {"roots": [".github/", "docs/", "artifacts/"],
                          "gate_input_directories": exceptions}
                self.write(RULES.POLICY_PATH, json.dumps(policy))
                self.base = self.commit()
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertIn("could not evaluate", result.stdout)

    def test_unicode_product_path_is_counted_and_accepted(self):
        self.write("docs/地図.md", "guide\n")
        self.commit()
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("1 added file(s), 0 violation(s)", result.stdout)

    def test_results_gate_input_is_explicit_but_artifacts_stay_reserved(self):
        policy = {"roots": [".github/", "src/", "tests/", "coverage/", "artifacts/"],
                  "gate_inputs": {"tests/results/matrix.v1.json": "Versioned release checker input"}}
        self.write(RULES.POLICY_PATH, json.dumps(policy))
        self.base = self.commit()
        loaded = RULES.load_policy(self.repo, self.base)
        self.assertIsNone(RULES.violation("tests/results/matrix.v1.json", loaded))
        for path in ("src/Results/output.json", "coverage/lcov.json", "tests/results/unpinned.json"):
            with self.subTest(path=path):
                self.assertEqual(RULES.violation(path, loaded),
                                 "run output must stay untracked under ignored artifacts/")
        policy["gate_inputs"]["artifacts/matrix.v1.json"] = "Cannot override the ignored output root"
        self.write(RULES.POLICY_PATH, json.dumps(policy))
        self.base = self.commit()
        with self.assertRaisesRegex(ValueError, "cannot override forbidden paths"):
            RULES.load_policy(self.repo, self.base)

    def test_bare_fetch_evaluates_paths_without_materializing_candidate_files(self):
        self.write("docs/archive/new.md", "candidate content\n")
        head = self.commit()
        self.git("config", "uploadpack.allowFilter", "true")
        self.git("config", "uploadpack.allowAnySHA1InWant", "true")
        bare = self.repo / "candidate.git"
        fetched = subprocess.run(["bash", str(ROOT / "fetch-candidate.sh"), str(bare),
                                  "file://" + str(self.repo), head], capture_output=True, text=True)
        self.assertEqual(fetched.returncode, 0, fetched.stderr)
        self.assertFalse((bare / "docs").exists())
        payload = self.git("rev-parse", f"{head}:docs/archive/new.md")
        policy = self.git("rev-parse", f"{head}^1:{RULES.POLICY_PATH}")
        missing = subprocess.check_output(["git", "-C", str(bare), "rev-list", "--objects",
                                           "--missing=print", "FETCH_HEAD"], text=True)
        self.assertIn("?" + payload, missing.splitlines())
        self.assertNotIn("?" + policy, missing.splitlines())
        subprocess.run(["git", "-C", str(bare), "remote", "set-url", "origin",
                        str(self.repo / "unavailable")], check=True)
        result = subprocess.run(["python3", "-I", str(ROOT / "check.py"), "--repo", str(bare),
                                 "--base", "FETCH_HEAD^1",
                                 "--head", "FETCH_HEAD"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("docs/archive/new.md", result.stdout)
        missing_after = subprocess.check_output(["git", "-C", str(bare), "rev-list", "--objects",
                                                 "--missing=print", "FETCH_HEAD"], text=True)
        self.assertIn("?" + payload, missing_after.splitlines())


if __name__ == "__main__":
    unittest.main()
