from dataclasses import dataclass
from enum import Enum
from functools import cached_property

from .correspondence import FileFunctions, pair_functions
from .git import FileChange, Repository, Revisions
from .lexing import language_of, lex_files
from .paths import GENERATED_OR_VENDORED, matches_any
from .tokens import Function, Lexed


class XmlDocPolicy(Enum):
    FORBID = "forbid"
    PUBLIC_SUMMARY = "public-summary"


@dataclass(frozen=True)
class CheckOptions:
    excludes: tuple[str, ...] = ()
    xml_docs: XmlDocPolicy = XmlDocPolicy.FORBID


class CheckContext:
    """The source files a PR adds or changes, read at base and head, with lazily lexed views."""

    def __init__(self, repository: Repository, revisions: Revisions, options: CheckOptions):
        self.repository = repository
        self.revisions = revisions
        self.options = options
        self.changes = [change for change in repository.changes(revisions) if self.is_checked(change)]
        self._function_pairs: dict[str, dict[Function, Function]] = {}

    def is_checked(self, change: FileChange) -> bool:
        excluded = matches_any(change.path, GENERATED_OR_VENDORED + self.options.excludes)
        is_source = change.head_is_regular_file and language_of(change.path) is not None
        return change.status != "D" and is_source and not excluded

    @cached_property
    def head_texts(self) -> dict[str, str]:
        """Head contents of the checked files that are readable UTF-8 text."""
        return readable_texts(self.repository, self.revisions.head, [change.path for change in self.changes])

    @cached_property
    def base_texts(self) -> dict[str, str]:
        """Base contents keyed by head path, for files that were regular source files before the PR."""
        existing = [change for change in self.changes if change.status != "A" and change.base_is_regular_file]
        by_old_path = readable_texts(self.repository, self.revisions.base, [change.old_path for change in existing])
        return {change.path: by_old_path[change.old_path] for change in existing if change.old_path in by_old_path}

    @cached_property
    def lexed(self) -> dict[str, Lexed]:
        """Head files that lexed cleanly; the others are listed in unchecked."""
        return _lexed_only(self.head_texts)

    @cached_property
    def base_lexed(self) -> dict[str, Lexed]:
        return _lexed_only(self.base_texts)

    def function_pairs(self, change: FileChange) -> dict[Function, Function]:
        """Each head function of the file mapped to the base function it continues; new functions are absent."""
        if change.path not in self._function_pairs:
            head = _file_functions(self.lexed.get(change.path), self.head_texts.get(change.path, ""))
            base = _file_functions(self.base_lexed.get(change.path), self.base_texts.get(change.path, ""))
            self._function_pairs[change.path] = pair_functions(change, head, base)
        return self._function_pairs[change.path]

    @cached_property
    def unchecked(self) -> list[str]:
        """Changed source files no rule saw: unreadable or unlexable at head."""
        return sorted(change.path for change in self.changes if change.path not in self.lexed)


def readable_texts(repository: Repository, revision: str, paths: list[str]) -> dict[str, str]:
    return {path: text for path, text in repository.read(revision, paths).items() if isinstance(text, str)}


def _lexed_only(texts: dict[str, str]) -> dict[str, Lexed]:
    return {path: result for path, result in lex_files(texts).items() if isinstance(result, Lexed)}


def _file_functions(lexed: Lexed | None, text: str) -> FileFunctions:
    return FileFunctions(lexed.functions if lexed else [], text.split("\n"))
