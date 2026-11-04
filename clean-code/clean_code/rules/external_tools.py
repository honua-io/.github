"""Runs ruff and ESLint on the PR's files at base and at head. A head finding is new unless the corresponding base
function had it at least as badly (function-level rules) or the unchanged line had it at base (line-level rules)."""

import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from ..budgets import BUDGETS
from ..catalog import RULES
from ..context import CheckContext
from ..correspondence import enclosing_function
from ..findings import Finding, Location
from ..git import FileChange
from ..lexing import PYTHON, TYPESCRIPT, language_of
from ..tokens import Function, Lexed

TOOL_DIRECTORY = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class _Tool:
    language: str
    command: Callable[[], list[str]]
    findings: Callable[[list[dict]], Iterator[Finding]]


def _ruff_command() -> list[str]:
    return [
        shutil.which("ruff") or "ruff", "check", "--config", str(TOOL_DIRECTORY / "ruff.toml"),
        "--config", f"lint.pylint.max-args={BUDGETS.parameters}",
        "--config", f"lint.mccabe.max-complexity={BUDGETS.complexity}",
        "--output-format", "json", "--no-cache", "--exit-zero",
    ]


def _eslint_command() -> list[str]:
    eslint = TOOL_DIRECTORY / "node_modules" / "eslint" / "bin" / "eslint.js"
    return ["node", str(eslint), "-c", str(TOOL_DIRECTORY / "eslint.config.mjs"), "--format", "json", "--no-warn-ignored"]


def _ruff_findings(results: list[dict]) -> Iterator[Finding]:
    for item in results:
        key = f"ruff/{item['code']}"
        if key in RULES:
            yield Finding.of(key, Location(item["filename"], item["location"]["row"]), item["message"])


def _eslint_findings(results: list[dict]) -> Iterator[Finding]:
    for report in results:
        for message in report["messages"]:
            key = f"eslint/{message.get('ruleId')}"
            if key in RULES:
                yield Finding.of(key, Location(report["filePath"], message.get("line", 1)), message["message"])


RUFF = _Tool(PYTHON.name, _ruff_command, _ruff_findings)
ESLINT = _Tool(TYPESCRIPT.name, _eslint_command, _eslint_findings)


def check_with_ruff(context: CheckContext) -> list[Finding]:
    return _introduced_findings(context, RUFF)


def check_with_eslint(context: CheckContext) -> list[Finding]:
    return _introduced_findings(context, ESLINT)


MEASURES = {
    "ruff/PLR0913": re.compile(r"\((\d+) > \d+\)"),
    "ruff/PLR0915": re.compile(r"\((\d+) > \d+\)"),
    "ruff/C901": re.compile(r"\((\d+) > \d+\)"),
    "eslint/max-params": re.compile(r"too many parameters \((\d+)\)"),
    "eslint/complexity": re.compile(r"complexity of (\d+)"),
    "eslint/sonarjs/cognitive-complexity": re.compile(r"Complexity from (\d+) to"),
}


def _introduced_findings(context: CheckContext, tool: _Tool) -> list[Finding]:
    paths = [change.path for change in context.changes if language_of(change.path).name == tool.language]
    head_texts = {path: context.head_texts[path] for path in paths if path in context.head_texts}
    if not head_texts:
        return []
    base_texts = {path: context.base_texts[path] for path in paths if path in context.base_texts}
    base_findings = _by_path(_run(tool, base_texts))
    changes = {change.path: change for change in context.changes}
    introduced = []
    for path, findings in _by_path(_run(tool, head_texts)).items():
        revisions = _FileRevisions(changes[path], context, base_findings.get(path, []))
        introduced += [finding for finding in findings if not revisions.consume_existing(finding)]
    return introduced


class _FileRevisions:
    """One file's functions at head and base, and the base findings not yet matched to a head finding."""

    def __init__(self, change: FileChange, context: CheckContext, base_findings: list[Finding]):
        self.change = change
        self.head_functions = _functions(context.lexed.get(change.path))
        self.base_functions = _functions(context.base_lexed.get(change.path))
        self.pairs = context.function_pairs(change)
        self.unmatched = _grouped(base_findings, lambda finding: finding.rule.key)

    def consume_existing(self, finding: Finding) -> bool:
        """True, and the base match is used up, when base already had this finding (or a worse one)."""
        candidates = self.unmatched.get(finding.rule.key, [])
        match = next((base for base in candidates if self._corresponds(finding, base)), None)
        if match is not None:
            candidates.remove(match)
        return match is not None

    def _corresponds(self, finding: Finding, base: Finding) -> bool:
        head_function = enclosing_function(finding.location.line, self.head_functions)
        if finding.rule.key in MEASURES and head_function is not None:
            counterpart = self.pairs.get(head_function)
            same_function = counterpart is not None and enclosing_function(base.location.line, self.base_functions) == counterpart
            return same_function and _measure(base) >= _measure(finding)
        return self.change.line_map.base_line(finding.location.line) == base.location.line


def _functions(lexed: Lexed | None) -> list[Function]:
    return lexed.functions if lexed else []


def _measure(finding: Finding) -> int:
    """The measured value in the rule's own message format, e.g. 'Too many arguments (6 > 4)' -> 6."""
    measured = MEASURES[finding.rule.key].search(finding.message)
    return int(measured.group(1)) if measured else 0


def _grouped(findings: list[Finding], key: Callable[[Finding], str]) -> dict[str, list[Finding]]:
    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        grouped.setdefault(key(finding), []).append(finding)
    return grouped


def _by_path(findings: list[Finding]) -> dict[str, list[Finding]]:
    return _grouped(findings, lambda finding: finding.location.path)


def _run(tool: _Tool, texts: dict[str, str]) -> list[Finding]:
    """Writes texts to a scratch tree, so the tool sees exactly that revision whatever the work tree holds."""
    if not texts:
        return []
    with tempfile.TemporaryDirectory(prefix="clean-code-") as scratch:
        root = Path(scratch).resolve()
        for path, text in texts.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        done = subprocess.run(tool.command() + list(texts), cwd=root, capture_output=True, text=True, check=False)
        if not done.stdout.strip().startswith("["):
            raise RuntimeError(f"{tool.language} linter failed: {done.stderr.strip()[:300]}")
        return [_relative(finding, root) for finding in tool.findings(json.loads(done.stdout))]


def _relative(finding: Finding, root: Path) -> Finding:
    path = str(Path(finding.location.path).resolve().relative_to(root))
    return Finding(finding.rule, Location(path, finding.location.line), finding.message)
