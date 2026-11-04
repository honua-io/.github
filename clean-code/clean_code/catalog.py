"""Every rule the check runs, keyed by tool and rule id, with the Clean Code smell it detects."""

from dataclasses import dataclass
from enum import Enum

from .budgets import BUDGETS as B


class Severity(Enum):
    BLOCK = "block"
    ADVISORY = "advisory"


@dataclass(frozen=True)
class Rule:
    key: str
    smell: str
    title: str
    languages: str
    severity: Severity = Severity.BLOCK

    @property
    def label(self) -> str:
        return f"{self.smell} {self.title}"


ADVISORY = Severity.ADVISORY
ALL = "all source"
CS = "C#"
PY = "Python"
TS = "TS/JS"

RULES = {
    rule.key: rule
    for rule in [
        Rule("clean-code/ticket-reference", "C1", "Ticket or PR reference in a comment", ALL),
        Rule("clean-code/history-comment", "C1", "Change history in a comment", ALL),
        Rule("clean-code/reviewer-note", "C1", "Reviewer note in a comment", ALL),
        Rule("clean-code/xml-doc", "C1", "XML doc comment in application code", CS),
        Rule("clean-code/redundant-comment", "C3", "Comment restates the next line of code", ALL, ADVISORY),
        Rule("clean-code/commented-out-code", "C5", "Commented-out code", f"{CS}, Terraform, shell"),
        Rule("ruff/ERA001", "C5", "Commented-out code", PY),
        Rule("eslint/sonarjs/no-commented-code", "C5", "Commented-out code", TS),
        Rule("clean-code/new-file-size", "Ch10", f"New file over {B.new_file_lines} lines", ALL),
        Rule("clean-code/large-file-growth", "Ch10", f"File over {B.large_file_lines} lines grew", ALL),
        Rule("clean-code/function-length", "G30", f"Function over {B.function_lines} lines", f"{PY}, {CS}, {TS}"),
        Rule("ruff/PLR0915", "G30", "Too many statements", PY, ADVISORY),
        Rule("ruff/C901", "G30", f"Cyclomatic complexity over {B.complexity}", PY, ADVISORY),
        Rule("eslint/complexity", "G30", f"Cyclomatic complexity over {B.complexity}", TS, ADVISORY),
        Rule("eslint/sonarjs/cognitive-complexity", "G30", f"Cognitive complexity over {B.cognitive_complexity}", TS, ADVISORY),
        Rule("eslint/max-depth", "G34", f"Nesting deeper than {B.nesting_depth}", TS, ADVISORY),
        Rule("clean-code/too-many-parameters", "F1", f"More than {B.parameters} parameters", CS),
        Rule("ruff/PLR0913", "F1", f"More than {B.parameters} parameters", PY),
        Rule("eslint/max-params", "F1", f"More than {B.parameters} parameters", TS),
        Rule("clean-code/flag-argument", "F3", "Boolean flag parameter", f"{CS}, {TS}"),
        Rule("ruff/FBT001", "F3", "Boolean flag parameter", PY),
        Rule("ruff/FBT002", "F3", "Boolean flag parameter with a default", PY),
        Rule("ruff/FBT003", "F3", "Boolean positional argument in a call", PY, ADVISORY),
        Rule("clean-code/duplication", "G5", f"Duplicated block ({B.duplicate_lines}+ lines, {B.duplicate_tokens}+ tokens)", ALL),
        Rule("eslint/sonarjs/no-identical-functions", "G5", "Identical functions", TS),
        Rule("ruff/PLR2004", "G25", "Magic number", PY, ADVISORY),
        Rule("eslint/no-magic-numbers", "G25", "Magic number", TS, ADVISORY),
        Rule("eslint/sonarjs/no-duplicate-string", "G25", "Duplicated string literal", TS, ADVISORY),
    ]
}


def markdown_table() -> str:
    lines = ["| Smell | Rule | Finds | Languages | Severity |", "| --- | --- | --- | --- | --- |"]
    for rule in sorted(RULES.values(), key=lambda rule: (rule.smell, rule.key)):
        lines.append(f"| {rule.smell} | `{rule.key}` | {rule.title} | {rule.languages} | {rule.severity.value} |")
    return "\n".join(lines)
