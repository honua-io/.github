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


def gate_input_directory(path, policy):
    for directory in policy.get("gate_input_directories", {}):
        if (path.startswith(directory)
                and not any(part.lower() in RESERVED_OUTPUT_DIRECTORIES for part in directory.split("/"))):
            return directory
    return None


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
    for field in ("gate_inputs", "gate_input_directories"):
        exceptions = policy.get(field, {})
        if not isinstance(exceptions, dict):
            raise ValueError("gate-input exceptions must be paths with reasons")
        if any(not isinstance(reason, str) or not reason.strip() for reason in exceptions.values()):
            raise ValueError("gate-input exceptions require reasons")
        directory = field == "gate_input_directories"
        for path in exceptions:
            if directory and (not path.endswith("/") or any(character in path for character in "*?[]{}\\")):
                raise ValueError("gate-input directories must be literal prefixes ending in /")
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
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Repository hygiene could not evaluate the PR: {type(error).__name__}")
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.decode("utf-8", errors="replace").strip())
        return 1
    findings = [(path, reason) for path in paths if (reason := violation(path, policy))]
    for path, reason in findings:
        print(f"{json.dumps(path, ensure_ascii=True)}: {reason}")
    print(f"Repository hygiene: {len(paths)} added file(s), {len(findings)} violation(s).")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
