"""Proves that a diff changes only comments and whitespace, by comparing code token streams."""

from dataclasses import dataclass
from enum import Enum

from .git import FileChange, Repository, Revisions
from .lexing import language_of, lex_files
from .tokens import Lexed, LexError, Token, code_stream


DOCSTRING_HINT = " (docstrings are code; declare docstring removal to delete a restating one)"


class DocstringPolicy(Enum):
    CODE = "docstrings are code"
    REMOVABLE = "docstrings may be deleted, not added or edited"


@dataclass(frozen=True)
class Verdict:
    path: str
    problem: str | None = None

    @property
    def comment_only(self) -> bool:
        return self.problem is None


def verify_diff(repository: Repository, revisions: Revisions, policy: DocstringPolicy) -> list[Verdict]:
    changes = repository.changes(revisions)
    problems = {change.path: _structural_problem(change) for change in changes}
    candidates = [path for path, problem in problems.items() if problem is None]
    base_lexed = lex_files(repository.read(revisions.base, candidates))
    head_lexed = lex_files(repository.read(revisions.head, candidates))
    return [
        Verdict(path, problem) if problem else _compare_file(path, (base_lexed[path], head_lexed[path]), policy)
        for path, problem in problems.items()
    ]


def _structural_problem(change: FileChange) -> str | None:
    if change.status != "M":
        return f"file status {change.status}: only in-place modifications can be comment-only"
    language = language_of(change.path)
    if not (language and language.verifiable):
        return "no verifying lexer for this file type"
    return None


def _compare_file(path: str, sides: tuple[Lexed | LexError, Lexed | LexError], policy: DocstringPolicy) -> Verdict:
    for name, lexed in zip(("base", "head"), sides):
        if isinstance(lexed, LexError):
            return Verdict(path, f"{name} does not lex: {lexed}")
    return Verdict(path, compare_lexed(*sides, policy))


@dataclass(frozen=True)
class _CodeSide:
    tokens: list[Token]
    stream: list[tuple[str, str]]

    @classmethod
    def of(cls, lexed: Lexed, policy: DocstringPolicy) -> "_CodeSide":
        tokens = _code_tokens(lexed, policy)
        return cls(tokens, code_stream(lexed, tokens))

    def describe(self, index: int) -> str:
        if index >= len(self.tokens):
            return "<end of file>"
        token = self.tokens[index]
        kind = "docstring " if token.is_docstring else ""
        separator = {"\n": "after a line break ", " ": "after a space "}.get(self.stream[index][1], "")
        return f"line {token.line}: {kind}{separator}{token.text[:60]!r}"


def compare_lexed(base: Lexed, head: Lexed, policy: DocstringPolicy) -> str | None:
    """None when base and head have the same code; otherwise where they first differ."""
    base_side, head_side = _CodeSide.of(base, policy), _CodeSide.of(head, policy)
    if base_side.stream != head_side.stream:
        return _first_difference(base_side, head_side)
    if policy is DocstringPolicy.REMOVABLE:
        return _docstring_edit(base, head)
    return None


def _code_tokens(lexed: Lexed, policy: DocstringPolicy) -> list[Token]:
    if policy is DocstringPolicy.CODE:
        return lexed.tokens
    kept, after_docstring = [], False
    for token in lexed.tokens:
        skip = token.is_docstring or (after_docstring and token.text == "NEWLINE")
        after_docstring = token.is_docstring
        if not skip:
            kept.append(token)
    return kept


def _docstring_edit(base: Lexed, head: Lexed) -> str | None:
    remaining = iter(token.text for token in base.tokens if token.is_docstring)
    for token in head.tokens:
        if token.is_docstring and token.text not in remaining:
            return f"head line {token.line}: docstring added or edited; only deleting a docstring is allowed"
    return None


def _first_difference(base: _CodeSide, head: _CodeSide) -> str:
    pairs = zip(base.stream, head.stream)
    index = next((i for i, (left, right) in enumerate(pairs) if left != right), min(len(base.stream), len(head.stream)))
    message = f"code differs: base {base.describe(index)} vs head {head.describe(index)}"
    docstring_involved = any(index < len(side.tokens) and side.tokens[index].is_docstring for side in (base, head))
    return message + (DOCSTRING_HINT if docstring_involved else "")
