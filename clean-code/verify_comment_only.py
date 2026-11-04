"""Exits 0 only when every file changed between --base and --head differs in comments and whitespace alone."""

import argparse
import sys
from pathlib import Path

# Run with python3 -I so the checked repository cannot shadow modules; -I drops this directory from sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from clean_code.comment_only import DocstringPolicy, verify_diff
from clean_code.git import Repository, Revisions


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base revision")
    parser.add_argument("--head", default="HEAD", help="head revision")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--allow-docstring-removal", action="store_true",
        help="let Python docstrings be deleted (never added or edited); declare this in the PR",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = parse_arguments(argv)
    policy = DocstringPolicy.REMOVABLE if arguments.allow_docstring_removal else DocstringPolicy.CODE
    verdicts = verify_diff(Repository(arguments.repo), Revisions(arguments.base, arguments.head), policy)
    for verdict in verdicts:
        print(f"{'ok  ' if verdict.comment_only else 'FAIL'} {verdict.path}{'' if verdict.comment_only else ': ' + verdict.problem}")
    failed = [verdict for verdict in verdicts if not verdict.comment_only]
    print(f"{len(verdicts) - len(failed)} of {len(verdicts)} changed files are comment-only ({policy.value}).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
