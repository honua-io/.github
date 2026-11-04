"""G30, F1 and F3 as a ratchet: a touched function may not newly exceed a budget or gain a flag parameter."""

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass

from ..budgets import BUDGETS
from ..context import CheckContext
from ..findings import Finding, Location
from ..git import FileChange
from ..lexing import CSHARP, PYTHON, TYPESCRIPT, language_of
from ..paths import is_test_path
from ..tokens import Function, Lexed

PARAMETER_COUNT_LANGUAGES = frozenset({CSHARP.name})
FLAG_ARGUMENT_LANGUAGES = frozenset({CSHARP.name, TYPESCRIPT.name, PYTHON.name})


@dataclass(frozen=True)
class _FunctionChange:
    """A function the PR touches, the same-named functions at base, and the first added line inside it."""

    head: Function
    base: tuple[Function, ...]
    location: Location

    @property
    def base_length(self) -> int:
        return max((function.length for function in self.base), default=0)

    @property
    def base_parameter_count(self) -> int:
        return max((len(function.parameters) for function in self.base), default=0)

    @property
    def base_flags(self) -> set[str]:
        return {parameter.name for function in self.base for parameter in function.parameters if parameter.is_boolean}


def check_functions(context: CheckContext) -> Iterator[Finding]:
    for change in context.changes:
        lexed = context.lexed.get(change.path)
        if lexed is not None:
            yield from _file_findings(change, lexed, context.base_lexed.get(change.path))


def _file_findings(change: FileChange, lexed: Lexed, base: Lexed | None) -> Iterator[Finding]:
    language = language_of(change.path).name
    base_by_name: dict[str, list[Function]] = defaultdict(list)
    for function in base.functions if base else []:
        base_by_name[function.name].append(function)
    for function in lexed.functions:
        added = [line for line in range(function.start, function.end + 1) if line in change.added_lines]
        if added:
            touched = _FunctionChange(function, tuple(base_by_name[function.name]), Location(change.path, added[0]))
            yield from _length_findings(touched)
            yield from _parameter_findings(touched, language)


def _length_findings(touched: _FunctionChange) -> Iterator[Finding]:
    length = touched.head.length
    if length > BUDGETS.function_lines and length > touched.base_length:
        message = f"{touched.head.name} is {length} lines; extract steps"
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
    for parameter in head.parameters:
        if parameter.is_boolean and parameter.name not in touched.base_flags:
            message = f"{head.name}({parameter.name}): split into two intention-revealing functions"
            yield Finding.of("clean-code/flag-argument", touched.location, message)
