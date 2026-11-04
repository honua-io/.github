"""Checks the lines a PR adds against the Clean Code rules in clean_code/catalog.py."""

import argparse
import json
import os
import sys
from pathlib import Path

# Run with python3 -I so the checked repository cannot shadow modules; -I drops this directory from sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from clean_code.check import run_checks
from clean_code.comment_only import DocstringPolicy, Verdict, verify_diff
from clean_code.context import CheckContext, CheckOptions, XmlDocPolicy
from clean_code.git import Repository, Revisions
from clean_code.report import Report, declarations, quality_exceptions


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base revision")
    parser.add_argument("--head", default="HEAD", help="head revision")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--pr-body", type=Path, help="file holding the PR description")
    parser.add_argument("--exclude", action="append", default=[], help="extra glob of paths to skip")
    parser.add_argument("--frozen", action="append", default=[], help="glob of files that may not be added or grow")
    parser.add_argument("--xml-docs", choices=[policy.value for policy in XmlDocPolicy], default="forbid")
    parser.add_argument("--json", type=Path, help="also write the findings as JSON here")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = parse_arguments(argv)
    options = CheckOptions(tuple(arguments.exclude), XmlDocPolicy(arguments.xml_docs), tuple(arguments.frozen))
    context = CheckContext(Repository(arguments.repo), Revisions(arguments.base, arguments.head), options)
    pr_body = arguments.pr_body.read_text() if arguments.pr_body else ""
    report = Report(run_checks(context), quality_exceptions(pr_body), context.unchecked)
    report.comment_only_verdicts = _declared_comment_only(context, declarations(pr_body))
    print("\n".join(report.annotations()))
    _write_summary(report.summary())
    if arguments.json:
        arguments.json.write_text(json.dumps(_as_json(report), indent=2))
    return 0 if report.passed else 1


def _declared_comment_only(context: CheckContext, declared: set[str]) -> list[Verdict] | None:
    """Runs the comment-only verifier when the PR body declares `clean-code: comment-only`."""
    if "comment-only" not in declared:
        return None
    policy = DocstringPolicy.REMOVABLE if "docstring-removal" in declared else DocstringPolicy.CODE
    return verify_diff(context.repository, context.revisions, policy)


def _write_summary(summary: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary_file:
            summary_file.write(summary)
    print(summary)


def _as_json(report: Report) -> dict:
    findings = [
        {"smell": finding.rule.smell, "rule": finding.rule.key, "blocking": finding.blocking,
         "path": finding.location.path, "line": finding.location.line, "message": finding.message}
        for finding in report.findings
    ]
    return {"passed": report.passed, "exceptions": report.exceptions, "unchecked": report.unchecked, "findings": findings}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
