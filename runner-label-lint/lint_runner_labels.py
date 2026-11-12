"""Fails when a job reachable from a fork pull request or workflow_run could run on a self-hosted runner.

Workflow files are read as YAML data only; nothing in the checked repository is executed.
"""

import argparse
from pathlib import Path
import sys

# Run with python3 -I so the checked repository cannot shadow modules; -I drops this directory from sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import yaml  # noqa: F401 - checked here so a missing PyYAML fails with a clear message
except ModuleNotFoundError:
    sys.exit("runner-label-lint: PyYAML is not installed for this Python (apt python3-yaml or pip PyYAML)")

from runner_labels.policy import DEFAULT_DENIED, LabelPolicy
from runner_labels.runs_on import Finding, check_workflow
from runner_labels.workflows import load_repository

ANNOTATION_ESCAPES = {"%": "%25", "\r": "%0D", "\n": "%0A"}
PROPERTY_ESCAPES = {**ANNOTATION_ESCAPES, ":": "%3A", ",": "%2C"}


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="checked-out repository root")
    parser.add_argument("--allow-label", action="append", default=[],
                        help="extra GitHub-hosted label, such as an organization larger runner")
    parser.add_argument("--deny-label", action="append", default=[], help="extra label that is never hosted")
    parser.add_argument("--annotations", action="store_true", help="print GitHub error and warning annotations")
    parser.add_argument("--strict-untrusted-events", action="store_true",
                        help="also fail on issue_comment, issues and discussion findings, which are advisory by default")
    return parser.parse_args(argv)


def lint(repository, labels):
    workflows, errors = load_repository(repository)
    findings = [Finding(error.path, error.line, f"cannot be checked: {error}", "fix the workflow file") for error in errors]
    for workflow in workflows.values():
        findings += check_workflow(workflow, labels)
    return sorted(findings, key=lambda finding: (finding.path, finding.line))


def _escape(text, escapes):
    return "".join(escapes.get(character, character) for character in text)


def annotation(finding):
    properties = f"file={_escape(finding.path, PROPERTY_ESCAPES)},line={finding.line}"
    return f"::{finding.severity} {properties}::{_escape(f'{finding.message}. Fix: {finding.hint}.', ANNOTATION_ESCAPES)}"


def main(argv):
    arguments = parse_arguments(argv)
    labels = LabelPolicy(allowed=frozenset(label.lower() for label in arguments.allow_label),
                         denied=DEFAULT_DENIED | {label.lower() for label in arguments.deny_label})
    findings = lint(arguments.repo, labels)
    for finding in findings:
        print(annotation(finding) if arguments.annotations else finding)
    failing = [finding for finding in findings if arguments.strict_untrusted_events or not finding.is_advisory]
    print(f"runner-label-lint: {len(failing)} failing, {len(findings) - len(failing)} advisory finding(s)")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
