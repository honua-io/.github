import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


POLICY_PATH = ".github/hygiene.json"
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


def ownership_findings(repo, base, head):
    paths = git_output(repo, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z",
                       base, head, "--").decode("utf-8", errors="surrogateescape").split("\0")[:-1]
    findings = []
    for path in paths:
        if trunk_owned(path):
            findings.append((path, "derived file is owned by trunk/release automation"))
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
    arguments = parser.parse_args()
    try:
        policy = load_policy(arguments.repo, arguments.base)
        paths = added_paths(arguments.repo, arguments.base, arguments.head)
        findings = ownership_findings(arguments.repo, arguments.base, arguments.head)
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
