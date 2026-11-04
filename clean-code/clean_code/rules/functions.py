"""G30, F1 and F3 as a ratchet: a touched function may not exceed a budget further than its base counterpart did,
nor gain a boolean flag parameter."""

from collections.abc import Iterator
from dataclasses import dataclass

from ..budgets import BUDGETS
from ..context import CheckContext
from ..findings import Finding, Location
from ..git import FileChange
from ..lexing import CSHARP, PYTHON, TYPESCRIPT, language_of
from ..paths import is_test_path
from ..tokens import Function

PARAMETER_COUNT_LANGUAGES = frozenset({CSHARP.name})
FLAG_ARGUMENT_LANGUAGES = frozenset({CSHARP.name, TYPESCRIPT.name, PYTHON.name})


@dataclass(frozen=True)
class _FunctionChange:
    """A function the PR touches, the base function it came from (None when new), and its first added line."""

    head: Function
    base: Function | None
    location: Location

    @property
    def base_length(self) -> int:
        return self.base.length if self.base else 0

    @property
    def base_parameter_count(self) -> int:
        return len(self.base.parameters) if self.base else 0

    def added_flags(self) -> list[str]:
        """Boolean parameters beyond the base count, preferring names the base did not have."""
        base_flags = [parameter.name for parameter in self.base.parameters if parameter.is_boolean] if self.base else []
        head_flags = [parameter.name for parameter in self.head.parameters if parameter.is_boolean]
        new_names = [name for name in head_flags if name not in base_flags]
        return list(dict.fromkeys(new_names + head_flags))[: max(0, len(head_flags) - len(base_flags))]


def check_functions(context: CheckContext) -> Iterator[Finding]:
    for change in context.changes:
        lexed = context.lexed.get(change.path)
        if lexed is not None:
            yield from _file_findings(change, lexed.functions, context.function_pairs(change))


def _file_findings(change: FileChange, functions: list[Function], pairs: dict[Function, Function]) -> Iterator[Finding]:
    language = language_of(change.path).name
    for function in functions:
        added = [line for line in range(function.start, function.end + 1) if line in change.added_lines]
        if added:
            touched = _FunctionChange(function, pairs.get(function), Location(change.path, added[0]))
            yield from _length_findings(touched)
            yield from _parameter_findings(touched, language)


def _length_findings(touched: _FunctionChange) -> Iterator[Finding]:
    """Newly over the budget, or over it already and grown by the growth budget or more."""
    length, base_length = touched.head.length, touched.base_length
    newly_over = length > BUDGETS.function_lines >= base_length
    grew_while_over = base_length > BUDGETS.function_lines and length - base_length >= BUDGETS.function_growth_lines
    if newly_over or grew_while_over:
        grew = f"grew from {base_length} to" if touched.base else "is"
        message = f"{touched.head.name} {grew} {length} lines; extract steps"
        yield Finding.of("clean-code/function-length", touched.location, message)


def _parameter_findings(touched: _FunctionChange, language: str) -> Iterator[Finding]:
    """Parameter rules skip tests, whose parameters are mostly data rows and injected fixtures."""
    if is_test_path(touched.location.path):
        return
    head = touched.head
    count = len(head.parameters)
    grew_too_many = count > BUDGETS.parameters and count > touched.base_parameter_count and not head.is_constructor
    if language in PARAMETER_COUNT_LANGUAGES and grew_too_many:
        message = f"{head.name} takes {count}; introduce a parameter object"
        yield Finding.of("clean-code/too-many-parameters", touched.location, message)
    if language not in FLAG_ARGUMENT_LANGUAGES:
        return
    for name in touched.added_flags():
        message = f"{head.name}({name}): split into two intention-revealing functions"
        yield Finding.of("clean-code/flag-argument", touched.location, message)
