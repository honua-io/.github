"""G30, F1 and F3 for functions the PR adds, read from each language's lexer."""

from collections.abc import Iterator

from ..budgets import BUDGETS
from ..context import CheckContext
from ..findings import Finding, Location
from ..lexing import CSHARP, TYPESCRIPT, language_of
from ..paths import is_test_path
from ..tokens import Function

PARAMETER_COUNT_LANGUAGES = frozenset({CSHARP.name})
FLAG_ARGUMENT_LANGUAGES = frozenset({CSHARP.name, TYPESCRIPT.name})


def check_functions(context: CheckContext) -> Iterator[Finding]:
    for change in context.changes:
        lexed = context.lexed.get(change.path)
        if lexed is None:
            continue
        language = language_of(change.path).name
        for function in lexed.functions:
            if function.start in change.added_lines:
                yield from _function_findings(Location(change.path, function.start), function, language)


def _function_findings(location: Location, function: Function, language: str) -> Iterator[Finding]:
    """Parameter rules skip tests, whose parameters are mostly data rows and injected fixtures."""
    if function.length > BUDGETS.function_lines:
        yield Finding.of("clean-code/function-length", location, f"{function.name} is {function.length} lines; extract steps")
    if is_test_path(location.path):
        return
    many_parameters = len(function.parameters) > BUDGETS.parameters and not function.is_constructor
    if language in PARAMETER_COUNT_LANGUAGES and many_parameters:
        message = f"{function.name} takes {len(function.parameters)}; introduce a parameter object"
        yield Finding.of("clean-code/too-many-parameters", location, message)
    if language in FLAG_ARGUMENT_LANGUAGES:
        for parameter in function.parameters:
            if parameter.is_boolean:
                message = f"{function.name}({parameter.name}): split into two intention-revealing functions"
                yield Finding.of("clean-code/flag-argument", location, message)
