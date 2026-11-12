"""Fails when a job reachable from a fork pull request or workflow_run could run on a self-hosted runner.

Workflow files are read as YAML data only; nothing in the checked repository is executed.
"""

import argparse
from pathlib import Path
import sys

# Run with python3 -I so the checked repository cannot shadow modules; -I drops this directory from sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
    parser.add_argument("--annotations", action="store_true", help="also print GitHub error annotations")
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
    return f"::error {properties}::{_escape(f'{finding.message}. Fix: {finding.hint}.', ANNOTATION_ESCAPES)}"


def main(argv):
    arguments = parse_arguments(argv)
    labels = LabelPolicy(allowed=frozenset(label.lower() for label in arguments.allow_label),
                         denied=DEFAULT_DENIED | {label.lower() for label in arguments.deny_label})
    findings = lint(arguments.repo, labels)
    for finding in findings:
        print(annotation(finding) if arguments.annotations else finding)
    print(f"runner-label-lint: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
