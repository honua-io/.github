"""Runs ruff and ESLint on the PR's files at base and at head; a head finding is new unless base has it too."""

import json
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from ..budgets import BUDGETS
from ..catalog import RULES
from ..context import CheckContext
from ..findings import Finding, Location
from ..lexing import PYTHON, TYPESCRIPT, language_of

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


def _introduced_findings(context: CheckContext, tool: _Tool) -> list[Finding]:
    """Head findings left after cancelling each against a base finding of the same rule on the same line text."""
    paths = [change.path for change in context.changes if language_of(change.path).name == tool.language]
    head_texts = {path: context.head_texts[path] for path in paths if path in context.head_texts}
    if not head_texts:
        return []
    base_texts = {path: context.base_texts[path] for path in paths if path in context.base_texts}
    existing = Counter(_anchor(finding, base_texts) for finding in _run(tool, base_texts))
    introduced = []
    for finding in _run(tool, head_texts):
        anchor = _anchor(finding, head_texts)
        if existing[anchor]:
            existing[anchor] -= 1
        else:
            introduced.append(finding)
    return introduced


def _anchor(finding: Finding, texts: dict[str, str]) -> tuple[str, str, str]:
    lines = texts[finding.location.path].split("\n")
    line_text = lines[finding.location.line - 1].strip() if finding.location.line <= len(lines) else ""
    return finding.rule.key, finding.location.path, line_text


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
