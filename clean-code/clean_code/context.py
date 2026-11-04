from dataclasses import dataclass
from enum import Enum
from functools import cached_property

from .git import FileChange, Repository, Revisions
from .lexing import language_of, lex_files
from .paths import GENERATED_OR_VENDORED, looks_minified, matches_any
from .tokens import Lexed


class XmlDocPolicy(Enum):
    FORBID = "forbid"
    PUBLIC_SUMMARY = "public-summary"


@dataclass(frozen=True)
class CheckOptions:
    excludes: tuple[str, ...] = ()
    xml_docs: XmlDocPolicy = XmlDocPolicy.FORBID


class CheckContext:
    """The source files a PR adds or changes, read at head, with lazily computed views."""

    def __init__(self, repository: Repository, revisions: Revisions, options: CheckOptions):
        self.repository = repository
        self.revisions = revisions
        self.options = options
        candidates = [change for change in repository.changes(revisions) if self.is_checked(change)]
        texts = readable_texts(repository, revisions.head, [change.path for change in candidates])
        self.minified = sorted(path for path, text in texts.items() if looks_minified(text))
        self.head_texts = {path: text for path, text in texts.items() if path not in self.minified}
        self.changes = [change for change in candidates if change.path not in self.minified]

    def is_checked(self, change: FileChange) -> bool:
        excluded = matches_any(change.path, GENERATED_OR_VENDORED + self.options.excludes)
        is_source = change.is_regular_file and language_of(change.path) is not None
        return change.status != "D" and is_source and not excluded

    @cached_property
    def base_texts(self) -> dict[str, str]:
        """Base contents keyed by head path, for files that existed before the PR."""
        existing = [change for change in self.changes if change.status != "A"]
        by_old_path = readable_texts(self.repository, self.revisions.base, [change.old_path for change in existing])
        return {change.path: by_old_path[change.old_path] for change in existing if change.old_path in by_old_path}

    @cached_property
    def lexed(self) -> dict[str, Lexed]:
        """Head files that lexed cleanly; the others are listed in unchecked."""
        results = lex_files(self.head_texts)
        return {path: result for path, result in results.items() if isinstance(result, Lexed)}

    @cached_property
    def unchecked(self) -> list[str]:
        """Changed source files no rule saw: unreadable, unlexable or minified."""
        return sorted(self.minified + [change.path for change in self.changes if change.path not in self.lexed])


def readable_texts(repository: Repository, revision: str, paths: list[str]) -> dict[str, str]:
    return {path: text for path, text in repository.read(revision, paths).items() if isinstance(text, str)}
