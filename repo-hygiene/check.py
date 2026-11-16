import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


POLICY_PATH = ".github/hygiene.json"
OWNERSHIP_REASON = "derived file is owned by trunk/release automation"
SCRATCH = re.compile(r"^(?:\.flow|\.?(?:scratch|scratchpad|tmp|temp|wip))(?:$|[-_.])", re.IGNORECASE)
HISTORY = re.compile(r"^\.?(?:evidence|audits?|archives?|reports?|receipts?|snapshots?|release-evidence)"
                     r"(?:$|[-_.])", re.IGNORECASE)
DATE = re.compile(r"(?<!\d)20\d{2}(?:[-_.]\d{2}(?:[-_.]\d{2})?|\d{4})(?!\d)")
BACKUP = re.compile(r"(?:\.(?:orig|rej|bak|backup|sw[pon])(?:\.\d+)?|~(?:\d+~)?)$", re.IGNORECASE)
OUTPUT_NOUN = r"(?:audit|evidence|report|receipt|snapshot|observation)"
OUTPUT = re.compile(rf"(?:^|[._-]){OUTPUT_NOUN}s?(?:$|[._-])", re.IGNORECASE)
PROSE_OUTPUT = re.compile(rf"(?:^|[._-])(?:{OUTPUT_NOUN}|observations)$", re.IGNORECASE)
OUTPUT_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml", ".md", ".txt", ".log", ".csv",
                   ".html", ".xml", ".png", ".zip"}
RESERVED_OUTPUT_DIRECTORIES = {"artifacts", "test-results", "testresults"}
RUN_DIRECTORIES = {"coverage", "results", "review-screenshots"}
SOURCE_ROOTS = {"src", "tests", "test", "scripts", "tools", "packages", "apps", "build", "eng"}
SOURCE_SUFFIXES = {".cs", ".py", ".sh", ".ps1", ".js", ".mjs", ".cjs", ".ts", ".tsx",
                   ".jsx", ".sql", ".go", ".rs", ".java", ".proto", ".swift", ".kt"}
TF_TOKEN = re.compile(r'//[^\n]*|\#[^\n]*|/\*.*?\*/|<<-?(\w+)\r?\n.*?^\s*\1\s*$|'
                      r'"(?:\\.|[^"\\])*"|[A-Za-z_]\w*|[^\s]', re.MULTILINE | re.DOTALL)


def trunk_owned(path):
    name = PurePosixPath(path).name
    return (bool(re.fullmatch(r"llms[^/]*\.txt", name)) or name == "CHANGELOG.md"
            or path.startswith(("samples/dist/", "api-report/"))
            or path == "docs/bundle-sizes.md")


def backend_blocks(text):
    tokens = [match.group() for match in TF_TOKEN.finditer(text)
              if not match.group().startswith(("//", "#", "/*"))]
    blocks = []
    for index, token in enumerate(tokens[:-2]):
        if token != "backend" or not re.fullmatch(r'"(?:\\.|[^"\\])*"|[A-Za-z_][\w-]*', tokens[index + 1]) or tokens[index + 2] != "{":
            continue
        depth = 1
        end = index + 3
        while end < len(tokens) and depth:
            depth += (tokens[end] == "{") - (tokens[end] == "}")
            end += 1
        if depth:
            raise ValueError("unterminated Terraform backend block")
        blocks.append(tuple(tokens[index:end]))
    return blocks


def revision_text(repo, revision, path):
    # Missing paths are expected on additions/deletions; other Git failures must fail closed.
    paths = git_output(repo, "ls-tree", "-z", "--name-only", revision, "--", path).split(b"\0")
    if path.encode("utf-8", errors="surrogateescape") not in paths:
        return ""
    return git_output(repo, "show", f"{revision}:{path}").decode("utf-8")


def release_changelog_allowed(repo, head, event_path):
    if event_path is None:
        return False
    event = json.loads(event_path.read_text())
    pr = event.get("pull_request", {})
    author = pr.get("user", {})
    sender = event.get("sender", {})
    identities = {"honua-io-bot[bot]": 321210756, "github-actions[bot]": 41898282}
    identity = identities.get(author.get("login"))
    if identity is None or author.get("type") != "Bot" or author.get("id") != identity:
        return False
    repository = event.get("repository", {}).get("full_name")
    base = pr.get("base", {})
    candidate = pr.get("head", {})
    if not repository or any(ref.get("repo", {}).get("full_name") != repository
                             for ref in (base, candidate)):
        return False
    branch = base.get("ref", "")
    prefix = f"release-please--branches--{branch}"
    release_ref = candidate.get("ref", "")
    if not branch or not (release_ref == prefix or
                          re.fullmatch(re.escape(prefix) + r"--components--[A-Za-z0-9._-]+", release_ref)):
        return False
    # Bind trusted event metadata to the fetched PR merge tree, never a later branch tip.
    parents = git_output(repo, "rev-list", "--parents", "-n", "1", head).decode().split()
    merge_fields = 3  # Merge SHA plus its two parents.
    if len(parents) != merge_fields or parents[2] != candidate.get("sha"):
        return False
    if sender.get("type") == "Bot" and sender.get("id") == identity:
        return True
    # A maintainer event grants no ownership exception by itself. Authenticate
    # every changed changelog against the original, signed release-bot commit.
    if sender.get("type") != "User" or not isinstance(sender.get("id"), int) or sender["id"] <= 0:
        return False
    return repaired_release_changelogs(repo, parents, event)


def verified_release_commit(repository, sha, author):
    if not os.environ.get("GH_TOKEN") or not re.fullmatch(r"honua-io/[A-Za-z0-9_.-]+", repository):
        return False
    try:
        result = subprocess.run(["gh", "api", "--hostname", "github.com",
                                 f"repos/{repository}/commits/{sha}"],
                                capture_output=True, check=True, timeout=30)
        commit = json.loads(result.stdout)
        verification = commit.get("commit", {}).get("verification", {})
        signer = commit.get("committer", {})
        creator = commit.get("author", {})
        web_flow_id = 19864447
        return (commit.get("sha") == sha and verification.get("verified") is True
                and verification.get("reason") == "valid"
                and signer.get("login") == "web-flow" and signer.get("id") == web_flow_id
                and signer.get("type") == "User"
                and all(creator.get(key) == author.get(key) for key in ("login", "id", "type")))
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def repaired_release_changelogs(repo, revisions, event):
    merge, base, candidate = revisions
    repository = event["repository"]["full_name"]
    author = event["pull_request"]["user"]
    # The shallow fetch retains at most four release/repair commits. Reject
    # incomplete or nonlinear histories rather than trusting author strings.
    limit = 4
    rows = git_output(repo, "rev-list", "--parents", f"--max-count={limit + 1}",
                      f"{base}..{candidate}").decode().splitlines()
    chain = [row.split() for row in rows]
    linear_fields = 2  # Commit SHA plus its single parent.
    if not chain or len(chain) > limit or any(len(row) != linear_fields for row in chain):
        return False
    if any(row[1] != next_row[0] for row, next_row in zip(chain, chain[1:])):
        return False
    ancestor = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                               chain[-1][1], base], capture_output=True, check=False)
    if ancestor.returncode != 0:
        return False
    changed = git_output(repo, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z",
                         base, merge, "--").decode("utf-8", errors="surrogateescape").split("\0")[:-1]
    paths = [path for path in changed if PurePosixPath(path).name == "CHANGELOG.md"
             and not path.startswith(("samples/dist/", "api-report/"))]
    if not paths:
        return False
    anchors = set()
    for path in paths:
        anchor = git_output(repo, "log", "-1", "--format=%H", candidate, "--", path).decode().strip()
        if anchor not in {row[0] for row in chain}:
            return False
        if git_output(repo, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z",
                      anchor, merge, "--", path):
            return False
        anchors.add(anchor)
    return all(verified_release_commit(repository, anchor, author) for anchor in sorted(anchors))



# Mirrors the SDK producer's publication allowlist. This permits ownership changes
# only; the trusted-base added-path policy remains independently enforced.
SDK_DERIVED_FILES = {
    "README.md", "bench/cross-sdk/corpus.json", "docs/bundle-sizes.md",
    "docs/comparison.md", "docs/errors.md", "docs/generated/mcp-eval-scorecard.md",
    "docs/generated/sample-catalog.md", "llms.txt", "llms-full.txt",
    "samples/catalog.v2.json", "samples/contract/v2/migrations/catalog.v1-to-v2.json",
    "samples/contract/v2/release-matrix-lanes.v1.json",
    *(f"samples/contract/v2/consumer-fixtures/honua-site-consumer.v{version}.json"
      for version in (2, 3, 4)),
}
SDK_DERIVED_PREFIXES = (
    "api-report/", "examples/migration-workbench/public/artifacts/",
    "examples/migration-workbench/src/generated/",
    "examples/ai-spatial-app-builder/evidence/",
    "examples/realtime-incident-dashboard/evidence/",
    "examples/spatial-analytics-workbench/evidence/", "samples/dist/",
    "samples/evidence/imagery-cog-quickstart/", "samples/evidence/maplibre-quickstart/",
    "samples/evidence/migration-workbench/", "samples/evidence/service-explorer/",
)


def sdk_derived_path(path):
    return (PurePosixPath(path).name != "CHANGELOG.md"
            and (path in SDK_DERIVED_FILES or path.startswith(SDK_DERIVED_PREFIXES)))


def sdk_derived_allowed(arguments):
    if arguments.event is None:
        return False
    event = json.loads(arguments.event.read_text())
    pr = event.get("pull_request", {})
    # The write-enabled producer validates the generated bundle before this App
    # publishes it. A branch name or commit author alone grants no exception.
    identities = {"honua-io-bot[bot]": 321210756, "github-actions[bot]": 41898282}
    author = pr.get("user", {})
    identity = identities.get(author.get("login"))
    if identity is None or any(user.get("id") != identity or user.get("type") != "Bot"
                               for user in (author, event.get("sender", {}))):
        return False
    repository = "honua-io/honua-sdk-js"
    source, candidate = pr.get("base", {}), pr.get("head", {})
    if (event.get("repository", {}).get("full_name") != repository
            or any(ref.get("repo", {}).get("full_name") != repository for ref in (source, candidate))
            or source.get("ref") != "trunk"
            or not re.fullmatch(r"automation/derived-artifacts-[1-9][0-9]*-[1-9][0-9]*",
                                candidate.get("ref", ""))):
        return False
    parents = git_output(arguments.repo, "rev-list", "--parents", "-n", "1", arguments.head).decode().split()
    base_sha = git_output(arguments.repo, "rev-parse", arguments.base).decode().strip()
    merge_fields = 3  # Merge SHA plus its two parents.
    if (len(parents) != merge_fields or parents[1] != base_sha or parents[1] != source.get("sha")
            or parents[2] != candidate.get("sha")):
        return False
    if not sdk_producer_chain(arguments.repo, base_sha, parents[2]):
        return False
    paths = git_output(arguments.repo, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z",
                       base_sha, parents[2], "--").decode("utf-8", errors="surrogateescape").split("\0")[:-1]
    return bool(paths) and all(sdk_derived_path(path) for path in paths)


def sdk_producer_chain(repo, base_sha, candidate_sha):
    # Five entries suffice to reject a chain beyond the producer's four commits.
    maximum_commits = 4
    linear_fields = 2  # Each commit SHA followed by its single parent.
    chain = git_output(repo, "rev-list", "--parents", f"--max-count={maximum_commits + 1}",
                       candidate_sha, "^" + base_sha).decode().splitlines()
    expected = candidate_sha
    if not 1 <= len(chain) <= maximum_commits:
        return False
    for line in chain:
        commit = line.split()
        if len(commit) != linear_fields or commit[0] != expected:
            return False
        subject = git_output(repo, "show", "-s", "--format=%s", commit[0]).decode().strip()
        if not re.fullmatch(r"chore\(evidence\): regenerate derived artifacts"
                            r"(?: \([a-z-]+\))? for [0-9a-f]{7,40}", subject):
            return False
        expected = commit[1]
    return expected == base_sha


def ownership_findings(repo, base, head):
    paths = git_output(repo, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z",
                       base, head, "--").decode("utf-8", errors="surrogateescape").split("\0")[:-1]
    findings = []
    for path in paths:
        if trunk_owned(path):
            findings.append((path, OWNERSHIP_REASON))
        if path.endswith(".tf"):
            before = backend_blocks(revision_text(repo, base, path))
            after = backend_blocks(revision_text(repo, head, path))
            if before != after:
                findings.append((path, "tracked Terraform backend blocks may not change in a PR"))
    return findings


def gate_input_directory(path, policy):
    return next((directory for directory in policy.get("gate_input_directories", {})
                 if path.startswith(directory)), None)


def forbidden_path(path, policy):
    parts = path.split("/")
    if not path or any(part in ("", ".", "..") for part in parts):
        return "invalid repository path"
    if any(ord(character) < ord(" ") for character in path):
        return "control character in repository path"
    if any(SCRATCH.search(part) for part in parts[:-1]) or SCRATCH.search(PurePosixPath(path).stem):
        return "scratch belongs outside tracked product files"
    if BACKUP.search(parts[-1]):
        return "editor or patch backup"
    reserved = {part.lower() for part in parts[:-1]} & RESERVED_OUTPUT_DIRECTORIES
    if reserved and (reserved != {"artifacts"} or not gate_input_directory(path, policy)):
        return "run output must stay untracked under ignored artifacts/"
    roots = policy["roots"]
    if not any(path.startswith(root) if root.endswith("/") else path == root for root in roots):
        return "unexpected top-level entry"
    return None


def product_sample_violation(path, policy):
    if path.startswith("samples/") and not policy.get("samples", False):
        return "product demonstrations belong in honua-samples"
    return None


def violation(path, policy):
    if reason := forbidden_path(path, policy):
        return reason
    if gate_input_directory(path, policy):
        return None
    if reason := product_sample_violation(path, policy):
        return reason
    if path in policy.get("gate_inputs", {}):
        return None
    parts = PurePosixPath(path).parts
    suffix = PurePosixPath(path).suffix.lower()
    workflow = path.startswith((".github/workflows/", "workflow-templates/")) and suffix in {".yml", ".yaml"}
    action = path.startswith(".github/actions/") and suffix in {".yml", ".yaml", ".sh", ".py", ".js"}
    issue_template = path.startswith(".github/ISSUE_TEMPLATE/") and suffix in {".yml", ".yaml", ".md"}
    source = parts[0] in SOURCE_ROOTS and suffix in SOURCE_SUFFIXES
    live_page = path in policy["roots"] and suffix == ".html"
    if source or workflow or action or issue_template or live_page:
        return None
    if any(part.lower() in RUN_DIRECTORIES for part in parts[:-1]):
        return "run output must stay untracked under ignored artifacts/"
    if any(HISTORY.search(part) for part in parts[:-1]):
        return "historical output belongs under ignored artifacts/"
    if DATE.search(path):
        return "date-stamped output belongs under ignored artifacts/"
    prose = suffix in {".md", ".html"}
    output_name = PROSE_OUTPUT.search(PurePosixPath(path).stem) if prose else OUTPUT.search(parts[-1])
    if suffix in OUTPUT_SUFFIXES and output_name:
        return "run output requires an exact gate-input exception"
    return None


def git_output(repo, *arguments):
    return subprocess.run(["git", "-C", str(repo), *arguments],
                          capture_output=True, check=True).stdout


def load_policy(repo, base):
    policy = json.loads(git_output(repo, "show", f"{base}:{POLICY_PATH}"))
    if not isinstance(policy, dict):
        raise ValueError("repository policy must be an object")
    roots = policy.get("roots")
    if not isinstance(roots, list) or not roots:
        raise ValueError("repository needs an explicit root allowlist")
    for root in roots:
        if not isinstance(root, str) or not re.fullmatch(r"[^/\\\x00-\x1f]+/?", root):
            raise ValueError("roots must be exact top-level files or directories ending in /")
        if root.rstrip("/") in (".", ".."):
            raise ValueError("invalid root entry")
    input_exceptions = {field: policy.get(field, {}) for field in ("gate_inputs", "gate_input_directories")}
    if any(not isinstance(exceptions, dict) for exceptions in input_exceptions.values()):
        raise ValueError("gate-input exceptions must be paths with reasons")
    for field, exceptions in input_exceptions.items():
        if any(not isinstance(reason, str) or not reason.strip() for reason in exceptions.values()):
            raise ValueError("gate-input exceptions require reasons")
        directory = field == "gate_input_directories"
        for path in exceptions:
            if directory and (not path.endswith("/") or any(character in path for character in "*?[]{}\\")):
                raise ValueError("gate-input directories must be literal prefixes ending in /")
            if directory and any(part.lower() in RESERVED_OUTPUT_DIRECTORIES for part in path.split("/")):
                raise ValueError("gate-input directory prefixes cannot contain reserved output directories")
            # Probe a descendant too so parent-directory bans apply to the prefix itself.
            if (forbidden_path(path[:-1] if directory else path, policy)
                    or (directory and forbidden_path(path + "gate-input", policy))
                    or (not directory and product_sample_violation(path, policy))):
                raise ValueError("gate-input exceptions cannot override forbidden paths or roots")
    if not isinstance(policy.get("samples", False), bool):
        raise ValueError("samples must be a boolean")
    return policy


def added_paths(repo, base, head):
    result = subprocess.run(["git", "-C", str(repo), "diff", "--no-ext-diff",
                             "--no-renames", "--name-only", "--diff-filter=A", "-z",
                             base, head, "--"],
                            capture_output=True, check=True)
    return result.stdout.decode("utf-8", errors="surrogateescape").split("\0")[:-1]


def main():
    parser = argparse.ArgumentParser(description="Check added PR paths using policy from the trusted base revision.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--event", type=Path, help="Trusted GitHub pull_request event payload (workflow only).")
    arguments = parser.parse_args()
    try:
        policy = load_policy(arguments.repo, arguments.base)
        paths = added_paths(arguments.repo, arguments.base, arguments.head)
        allow_changelog = release_changelog_allowed(arguments.repo, arguments.head, arguments.event)
        findings = ownership_findings(arguments.repo, arguments.base, arguments.head)
        if sdk_derived_allowed(arguments):
            findings = [finding for finding in findings
                        if finding[1] != OWNERSHIP_REASON or not sdk_derived_path(finding[0])]
        if allow_changelog:
            findings = [finding for finding in findings if PurePosixPath(finding[0]).name != "CHANGELOG.md"
                        or finding[0].startswith(("samples/dist/", "api-report/"))]
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Repository hygiene could not evaluate the PR: {type(error).__name__}")
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.decode("utf-8", errors="replace").strip())
        return 1
    findings.extend((path, reason) for path in paths if (reason := violation(path, policy)))
    for path, reason in findings:
        print(f"{json.dumps(path, ensure_ascii=True)}: {reason}")
    print(f"Repository hygiene: {len(paths)} added file(s), {len(findings)} violation(s).")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
