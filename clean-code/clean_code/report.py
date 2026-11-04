"""Turns findings into GitHub annotations, a job summary and an exit code; logs every quality exception."""

import re
from dataclasses import dataclass, field

from .findings import Finding

QUALITY_EXCEPTION = re.compile(r"^\s*quality-exception:\s*(\S.*?)\s*$", re.IGNORECASE | re.MULTILINE)
SUMMARY_ROW_LIMIT = 200


def quality_exceptions(pr_body: str) -> list[str]:
    return QUALITY_EXCEPTION.findall(pr_body or "")


@dataclass
class Report:
    findings: list[Finding]
    exceptions: list[str]
    unchecked: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.blocking]

    @property
    def passed(self) -> bool:
        return not self.blocking or bool(self.exceptions)

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
            lines.append(f"- Not checked (unreadable, unlexable or minified): {listed}")
        if self.findings:
            lines += ["", "| Smell | Severity | Location | Finding |", "| --- | --- | --- | --- |"]
            lines += [_summary_row(finding) for finding in self.findings[:SUMMARY_ROW_LIMIT]]
        return "\n".join(lines) + "\n"

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
