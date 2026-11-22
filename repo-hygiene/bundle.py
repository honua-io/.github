"""Bundle policy and weekly exception accounting for trusted PR metadata."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess
import sys


MINIMUM_ISSUES = 3
MINIMUM_LINES = 300
PAGE_SIZE = 100
SEARCH_LIMIT = 1000
REFERENCE = r"(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#[1-9][0-9]*(?![A-Za-z0-9_])"
ISSUE_URL = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/issues/"
    r"([1-9][0-9]*)(?![A-Za-z0-9_])", re.IGNORECASE,
)
CLOSING = re.compile(
    rf"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+"
    rf"({REFERENCE}(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+){REFERENCE})*)",
    re.IGNORECASE,
)
# Main's standing rule (21 Nov 2026) allows one ticket, or two, when no third
# small ticket exists in the repository; the optional parenthetical dates it.
STANDING_RULE = (r"(?:single|two-ticket(?:[- ]bundle)?)[ \t]+authorized[ \t]+by[ \t]+main"
                 r"[ \t]+standing[ \t]+rule(?:[ \t]*\([^()\r\n]*\))?")
EXCEPTION = re.compile(
    r"^bundle-exception:[ \t]*(?:trunk-red|security[- ]high|blocking[- ]red|"
    rf"{STANDING_RULE})"
    r"[ \t]*(?:[:—–]| - )[ \t]*\S[^\r\n]*$", re.IGNORECASE | re.MULTILINE,
)
LANE = re.compile(r"^lane:\s*(s-[a-z0-9-]+)\s*$", re.IGNORECASE | re.MULTILINE)
RULE = ("Bundle rule: close at least 3 distinct issues, change at least 300 lines, "
        "or apply bundle-exception with a one-line "
        "'Bundle-exception: trunk-red|security high|blocking red|"
        "single authorized by main standing rule — reason' in the body. "
        "Bot authors are exempt.")


def prose(body):
    """Exclude quoted examples from policy metadata."""
    text = re.sub(r"<!--.*?-->", "", body or "", flags=re.DOTALL)
    text = re.sub(r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^ {0,3}\1[^\n]*$|\Z)", "", text)
    text = re.sub(r"(?<!`)(`+)(?!`)[\s\S]*?(?<!`)\1(?!`)", "", text)
    return "\n".join(line for line in text.splitlines() if not line.startswith(("    ", "\t")) and not line.lstrip().startswith(">"))


def closed_issues(body, repository):
    references = set()
    text = ISSUE_URL.sub(r"\1#\2", prose(body))
    for match in CLOSING.finditer(text):
        for reference in re.findall(REFERENCE, match.group(1)):
            owner, number = reference.rsplit("#", 1)
            references.add(((owner or repository).lower(), int(number)))
    return references


def has_exception(pr):
    labels = {label["name"] for label in pr.get("labels", [])}
    return "bundle-exception" in labels and bool(EXCEPTION.search(prose(pr.get("body"))))


def decision(pr, repository, changed_lines):
    if pr.get("user", {}).get("type") == "Bot":
        return True, "bot author"
    issues = len(closed_issues(pr.get("body"), repository))
    if issues >= MINIMUM_ISSUES:
        return True, f"{issues} distinct closing references"
    if changed_lines >= MINIMUM_LINES:
        return True, f"{changed_lines} changed lines"
    if has_exception(pr):
        return True, "documented bundle-exception"
    return False, f"{issues} distinct closing references; {changed_lines} changed lines. {RULE}"


def line_count(arguments):
    result = subprocess.run(
        ["git", "-C", str(arguments.repo), "diff", "--no-ext-diff", "--find-renames",
         "--numstat", "-z", arguments.base, arguments.head, "--"],
        check=True, capture_output=True,
    )
    # Binary changes have no line count. Count the exact fetched merge tree,
    # rather than trusting candidate-supplied metadata or checking out its code.
    records = iter(result.stdout.split(b"\0"))
    total = 0
    for record in records:
        if not record:
            continue
        added, deleted, path = record.split(b"\t", 2)
        if not path:
            next(records)  # NUL-delimited old and new paths for a rename.
            next(records)
        total += sum(int(count) for count in (added, deleted) if count != b"-")
    return total


def check(arguments):
    event = json.loads(arguments.event.read_text())
    pr = event["pull_request"]
    repository = event["repository"]["full_name"]
    passed, reason = decision(pr, repository, line_count(arguments))
    print(f"Bundle policy: {'PASS' if passed else 'FAIL'} — {reason}")
    return int(not passed)


def search_page(query, page):
    result = subprocess.run(
        ["gh", "api", "--method", "GET", "search/issues", "-f", f"q={query}",
         "-f", f"per_page={PAGE_SIZE}", "-f", f"page={page}"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def weekly_exceptions(since):
    query = f"org:honua-io is:pr is:merged label:bundle-exception merged:>={since}"
    items = []
    page = 1
    while True:
        result = search_page(query, page)
        if result.get("incomplete_results") or result["total_count"] > SEARCH_LIMIT:
            raise ValueError("exception search incomplete; narrow the reporting window")
        items.extend(result["items"])
        if len(items) >= result["total_count"]:
            return items
        if not result["items"]:
            raise ValueError("exception search ended before total_count")
        page += 1


def summary_text(items, since):
    counts = Counter()
    invalid = 0
    for item in items:
        match = LANE.search(prose(item.get("body")))
        lane = match.group(1).lower() if match else "unattributed (add Lane: s-name to PR body)"
        counts[lane] += 1
        invalid += int(not has_exception(item))
    rows = [f"Bundle exceptions merged since {since} (UTC)", "", "| Lane | PRs |",
            "| --- | ---: |"]
    rows.extend(f"| {lane} | {count} |" for lane, count in sorted(counts.items()))
    rows.extend(["", f"Total labelled PRs: {len(items)}; missing valid reason: {invalid}.",
                 "Counts reflect current labels and bodies on merged PRs; removed labels are absent."])
    return "\n".join(rows) + "\n"


def summary(arguments):
    since = arguments.since or (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    datetime.strptime(since, "%Y-%m-%d")
    print(summary_text(weekly_exceptions(since), since), end="")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    policy = commands.add_parser("check")
    policy.add_argument("--repo", type=Path, required=True)
    policy.add_argument("--base", required=True)
    policy.add_argument("--head", required=True)
    policy.add_argument("--event", type=Path, required=True)
    report = commands.add_parser("summary")
    report.add_argument("--since", help="First UTC merge date (YYYY-MM-DD); defaults to seven days ago.")
    arguments = parser.parse_args()
    try:
        return check(arguments) if arguments.command == "check" else summary(arguments)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"Bundle policy could not evaluate: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
