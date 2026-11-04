import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from .dialects import CSharpScanner, HclScanner, ShellScanner
from .python_lexer import lex_python
from .tokens import Lexed, LexError
from .typescript import lex_typescript_files


@dataclass(frozen=True)
class Language:
    name: str
    lex: Callable[[str], Lexed] | None
    verifiable: bool


LONE_CARRIAGE_RETURN = re.compile(r"\r(?!\n)")


def _lf_or_crlf_only(lex: Callable[[str], Lexed]) -> Callable[[str], Lexed]:
    """Python and HCL disagree on what a lone CR ends, so such files are refused rather than guessed at."""

    def lex_checked(text: str) -> Lexed:
        if LONE_CARRIAGE_RETURN.search(text):
            raise LexError("lone carriage-return line endings are not supported")
        return lex(text)

    return lex_checked


CSHARP = Language("csharp", lambda text: CSharpScanner(text).lex(), verifiable=True)
RAZOR = Language("razor", CSHARP.lex, verifiable=False)
C_FAMILY = Language("c-family", CSHARP.lex, verifiable=False)
PYTHON = Language("python", _lf_or_crlf_only(lex_python), verifiable=True)
TYPESCRIPT = Language("typescript", None, verifiable=True)
TERRAFORM = Language("terraform", _lf_or_crlf_only(lambda text: HclScanner(text).lex()), verifiable=True)
SHELL = Language("shell", lambda text: ShellScanner(text).lex(), verifiable=False)

LANGUAGE_BY_SUFFIX = {
    **dict.fromkeys([".cs", ".csx"], CSHARP),
    **dict.fromkeys([".razor", ".cshtml"], RAZOR),
    **dict.fromkeys(
        [".java", ".kt", ".kts", ".go", ".swift", ".rs", ".scala", ".c", ".h", ".cc", ".cpp", ".hpp", ".proto", ".dart"],
        C_FAMILY,
    ),
    **dict.fromkeys([".py", ".pyi"], PYTHON),
    **dict.fromkeys([".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"], TYPESCRIPT),
    **dict.fromkeys([".tf", ".tfvars", ".hcl"], TERRAFORM),
    **dict.fromkeys([".sh", ".bash", ".zsh", ".ps1", ".psm1"], SHELL),
}


def language_of(path: str) -> Language | None:
    return LANGUAGE_BY_SUFFIX.get(PurePosixPath(path).suffix.lower())


def lex_files(texts: dict[str, str | Exception]) -> dict[str, Lexed | LexError]:
    """Lexes every source file in texts; files in other languages are left out, unreadable ones are errors."""
    readable = {path: text for path, text in texts.items() if isinstance(text, str)}
    results = {path: LexError(str(text)) for path, text in texts.items() if not isinstance(text, str)}
    results |= lex_typescript_files({path: text for path, text in readable.items() if language_of(path) is TYPESCRIPT})
    for path, text in readable.items():
        language = language_of(path)
        if language and language.lex:
            results[path] = _lex_one(language, text)
    return results


def _lex_one(language: Language, text: str) -> Lexed | LexError:
    try:
        return language.lex(text)
    except LexError as error:
        return error
