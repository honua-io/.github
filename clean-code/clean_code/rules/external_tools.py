"""Runs ruff and ESLint on the PR's files as they are at head, keeping findings on added lines."""

import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

from ..budgets import BUDGETS
from ..catalog import RULES
from ..context import CheckContext
from ..findings import Finding, Location
from ..lexing import PYTHON, TYPESCRIPT, language_of

TOOL_DIRECTORY = Path(__file__).resolve().parents[2]
RUFF_SETTINGS = (
    "--config", str(TOOL_DIRECTORY / "ruff.toml"),
    "--config", f"lint.pylint.max-args={BUDGETS.parameters}",
    "--config", f"lint.mccabe.max-complexity={BUDGETS.complexity}",
)
ESLINT = TOOL_DIRECTORY / "node_modules" / "eslint" / "bin" / "eslint.js"


def check_with_ruff(context: CheckContext) -> Iterator[Finding]:
    paths = _paths_in(context, PYTHON.name)
    if not paths:
        return
    command = [shutil.which("ruff") or "ruff", "check", *RUFF_SETTINGS, "--output-format", "json", "--no-cache", "--exit-zero"]
    for item in _run_on_head_copies(context, command + paths):
        location = item["location"]["row"]
        yield from _finding(context, f"ruff/{item['code']}", Location(item["filename"], location), item["message"])


def check_with_eslint(context: CheckContext) -> Iterator[Finding]:
    paths = _paths_in(context, TYPESCRIPT.name)
    if not paths:
        return
    command = ["node", str(ESLINT), "-c", str(TOOL_DIRECTORY / "eslint.config.mjs"), "--format", "json", "--no-warn-ignored"]
    for report in _run_on_head_copies(context, command + paths):
        for message in report["messages"]:
            location = Location(report["filePath"], message.get("line", 1))
            yield from _finding(context, f"eslint/{message.get('ruleId')}", location, message["message"])


def _paths_in(context: CheckContext, language: str) -> list[str]:
    return [change.path for change in context.changes if language_of(change.path).name == language]


def _run_on_head_copies(context: CheckContext, command: list[str]) -> list[dict]:
    """Writes the head versions to a scratch tree, so the tools see head even when the work tree differs."""
    with tempfile.TemporaryDirectory(prefix="clean-code-") as scratch:
        for path, text in context.head_texts.items():
            target = Path(scratch, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        done = subprocess.run(command, cwd=scratch, capture_output=True, text=True, check=False)
        if not done.stdout.strip().startswith("["):
            raise RuntimeError(f"{Path(command[0]).name} failed: {done.stderr.strip()[:300]}")
        results = json.loads(done.stdout)
        for result in results:
            for field in ("filename", "filePath"):
                if field in result:
                    result[field] = str(Path(result[field]).resolve().relative_to(Path(scratch).resolve()))
        return results


def _finding(context: CheckContext, key: str, location: Location, message: str) -> Iterator[Finding]:
    change = next(change for change in context.changes if change.path == location.path)
    if key in RULES and location.line in change.added_lines:
        yield Finding.of(key, location, message)
