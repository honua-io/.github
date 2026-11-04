"""Turns findings into GitHub annotations, a job summary and an exit code; logs every quality exception."""

import re
from dataclasses import dataclass, field

from .comment_only import Verdict
from .findings import Finding

QUALITY_EXCEPTION = re.compile(r"^\s*quality-exception:\s*(\S.*?)\s*$", re.IGNORECASE | re.MULTILINE)
DECLARATION = re.compile(r"^\s*clean-code:\s*([\w-]+)\s*$", re.IGNORECASE | re.MULTILINE)
SUMMARY_ROW_LIMIT = 200


def quality_exceptions(pr_body: str) -> list[str]:
    return QUALITY_EXCEPTION.findall(pr_body or "")


def declarations(pr_body: str) -> set[str]:
    """Lines such as `clean-code: comment-only`, each alone on its line; prose mentioning them does not count."""
    return {name.lower() for name in DECLARATION.findall(pr_body or "")}


@dataclass
class Report:
    findings: list[Finding]
    exceptions: list[str]
    unchecked: list[str] = field(default_factory=list)
    comment_only_verdicts: list[Verdict] | None = None

    @property
    def blocking(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.blocking]

    @property
    def disproved_comment_only(self) -> list[Verdict]:
        return [verdict for verdict in self.comment_only_verdicts or [] if not verdict.comment_only]

    @property
    def passed(self) -> bool:
        return (not self.blocking or bool(self.exceptions)) and not self.disproved_comment_only

    def annotations(self) -> list[str]:
        return [self._annotation(finding) for finding in self.findings]

    def _annotation(self, finding: Finding) -> str:
        level = "notice" if not finding.blocking else "warning" if self.exceptions else "error"
        location = finding.location
        title = _escape_property(finding.rule.label)
        return f"::{level} file={location.path},line={location.line},title={title}::{_escape_data(finding.message)}"

    def summary(self) -> str:
        lines = ["## Clean code", "", self._verdict(), ""]
        for reason in self.exceptions:
            lines.append(f"- **quality-exception:** {reason}")
        if self.unchecked:
            listed = ", ".join(f"`{path}`" for path in self.unchecked)
            lines.append(f"- Not checked (unreadable or unlexable): {listed}")
        lines += self._comment_only_lines()
        if self.findings:
            lines += ["", "| Smell | Severity | Location | Finding |", "| --- | --- | --- | --- |"]
            lines += [_summary_row(finding) for finding in self.findings[:SUMMARY_ROW_LIMIT]]
        return "\n".join(lines) + "\n"

    def _comment_only_lines(self) -> list[str]:
        if self.comment_only_verdicts is None:
            return []
        disproved = self.disproved_comment_only
        if not disproved:
            return [f"- Declared comment-only: proven for all {len(self.comment_only_verdicts)} changed files."]
        return [f"- Declared comment-only, but **not proven** for {len(disproved)} files:"] + [
            f"  - `{verdict.path}`: {verdict.problem}" for verdict in disproved
        ]

    def _verdict(self) -> str:
        counts = f"{len(self.blocking)} blocking, {len(self.findings) - len(self.blocking)} advisory"
        if not self.blocking:
            return f"Passed: {counts}."
        if self.exceptions:
            return f"Passed under a quality exception: {counts}."
        return f"Failed: {counts}. Fix them, or add `quality-exception: <reason>` to the PR body."


def _summary_row(finding: Finding) -> str:
    severity = "block" if finding.blocking else "advisory"
    location = f"`{finding.location.path}:{finding.location.line}`"
    text = f"{finding.rule.title}: {finding.message}".replace("|", "\\|")
    return f"| {finding.rule.smell} | {severity} | {location} | {text} |"


def _escape_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text: str) -> str:
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")
