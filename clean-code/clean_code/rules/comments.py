"""C1, C3 and C5: what added comments may not contain."""

import re
from collections.abc import Iterator

from ..context import CheckContext, XmlDocPolicy
from ..findings import Finding, Location
from ..lexing import CSHARP, PYTHON, TYPESCRIPT, language_of
from ..tokens import Comment, Lexed

TICKET = re.compile(
    r"(?<![\w/#&])#\d+\b|\bhonua-[\w.-]+#\d+|\bSEC-\d+\b|github\.com/honua-io/[\w.-]+/(?:issues|pull)/\d+"
    r"|\b(?:PR|pull request|issue|ticket)\s*#?\d+\b",
    re.IGNORECASE,
)
HISTORY = re.compile(
    r"\b(?:previously|no longer|formerly|(?:was|were) (?:changed|renamed|removed)|used to be|now we|we now"
    r"|(?:we|it|this|that|they|which) used to|(?:we|team|founder) decided|decision(?=\s*:)|founder|R\d+|rc\.\d+)\b"
    r"|\b20\d{2}[-/]\d{2}[-/]\d{2}\b",
    re.IGNORECASE,
)
REVIEWER_NOTE = re.compile(
    r"\b(?:per|from|addresses|addressing|addressed)\s+(?:the\s+)?(?:code\s+|PR\s+)?review\b"
    r"|\breview(?:er)?\s+(?:note|feedback|comment|finding|request)s?\b"
    r"|\b(?:reviewer|Sol|Codex|Opus|Fable|Copilot)\s+(?:asked|requested|flagged|noted|suggested|wanted)\b"
    r"|\bMERGE-OK\b|\bas requested\b",
    re.IGNORECASE,
)
INAPPROPRIATE = (
    (TICKET, "clean-code/ticket-reference", "move the reference to the commit or PR"),
    (HISTORY, "clean-code/history-comment", "describe what the code does now; history belongs in git"),
    (REVIEWER_NOTE, "clean-code/reviewer-note", "reviewer notes belong in the PR thread"),
)
COMMENT_MARKERS = re.compile(r'^\s*(?:///?|/\*+|\*+/?|#+|"""|\'\'\')\s?|\s*\*+/\s*$|\s*(?:"""|\'\'\')\s*$')
LOOKS_LIKE_CODE = re.compile(
    r"^(?:(?:if|for|foreach|while|return|var|await|using|throw|new|public|private|protected|internal|static)\b.*[;{(=]"
    r"|[\w.\[\]]+\s*\(.*\)\s*;|.*[;{]\s*$|\}\s*$|[\w.-]+\s*=\s*[\"\w\[{].*[^.]$|export\s+\w+=)"
)
STATEMENT = re.compile(
    r"^(?:return\b.*;|(?:var|let|const|await)\s+\S.*[;=(]|new\s+\w+\(.*|(?:if|for|foreach|while|switch)\s*\(.*"
    r"|[\w.\[\]<>]+\s*=\s*\S.*;|[\w.\[\]<>]+\(.*\)\s*;)$"
)
STRING_LITERAL = re.compile(r'"[^"]*"|\'[^\']*\'')
PROSE = re.compile(r"\b[A-Za-z]+ [A-Za-z]+ [A-Za-z]+\b")
STOP_WORDS = frozenset("a an and as at be by for from if in into is it of on or the then this to with".split())
WORD = re.compile(r"[A-Za-z][a-z]+|[A-Z]+(?![a-z])")
MIN_RESTATED_WORDS = 2
NATIVE_COMMENTED_CODE = frozenset({PYTHON.name, TYPESCRIPT.name})


def check_comments(context: CheckContext) -> Iterator[Finding]:
    for change in context.changes:
        lexed = context.lexed.get(change.path)
        if lexed is None:
            continue
        added = [comment for comment in lexed.comments if comment.line in change.added_lines]
        yield from _inappropriate(change.path, added)
        yield from _redundant(change.path, added, lexed)
        yield from _xml_docs(change.path, added, context.options.xml_docs)
        if language_of(change.path).name not in NATIVE_COMMENTED_CODE:
            yield from _commented_out_code(change.path, added)


def comment_text(comment: Comment) -> str:
    return COMMENT_MARKERS.sub("", comment.text).strip()


def _inappropriate(path: str, comments: list[Comment]) -> Iterator[Finding]:
    for comment in comments:
        for pattern, key, advice in INAPPROPRIATE:
            match = pattern.search(comment.text)
            if match:
                yield Finding.of(key, Location(path, comment.line), f"'{match.group().strip()}': {advice}")


def _commented_out_code(path: str, comments: list[Comment]) -> Iterator[Finding]:
    for comment in comments:
        if not comment.text.lstrip().startswith("///") and _looks_like_code(comment_text(comment)):
            yield Finding.of("clean-code/commented-out-code", Location(path, comment.line), "delete it; git keeps it")


def _looks_like_code(text: str) -> bool:
    """A statement, or code-shaped and not a sentence (three plain words in a row outside string literals)."""
    if STATEMENT.match(text):
        return True
    return bool(LOOKS_LIKE_CODE.match(text)) and not PROSE.search(STRING_LITERAL.sub('""', text))


def _xml_docs(path: str, comments: list[Comment], policy: XmlDocPolicy) -> Iterator[Finding]:
    if language_of(path) is not CSHARP:
        return
    for block in _consecutive_blocks([comment for comment in comments if comment.text.lstrip().startswith("///")]):
        one_line_summary = len(block) == 1 and re.fullmatch(r"\s*///\s*<summary>.+</summary>\s*", block[0].text)
        if policy is XmlDocPolicy.PUBLIC_SUMMARY and one_line_summary:
            continue
        advice = "only a one-line <summary> on public SDK members" if policy is XmlDocPolicy.PUBLIC_SUMMARY else (
            "no XML docs in application code; let names carry the meaning")
        yield Finding.of("clean-code/xml-doc", Location(path, block[0].line), f"{len(block)}-line /// block: {advice}")


def _consecutive_blocks(comments: list[Comment]) -> list[list[Comment]]:
    blocks: list[list[Comment]] = []
    for comment in comments:
        if blocks and blocks[-1][-1].line == comment.line - 1:
            blocks[-1].append(comment)
        else:
            blocks.append([comment])
    return blocks


def _redundant(path: str, comments: list[Comment], lexed: Lexed) -> Iterator[Finding]:
    code_lines = sorted({token.line for token in lexed.tokens})
    words_by_line = _identifier_words_by_line(lexed)
    for comment in comments:
        words = {word for word in _words(comment_text(comment)) if word not in STOP_WORDS}
        next_line = next((line for line in code_lines if line > comment.line), None)
        if len(words) >= MIN_RESTATED_WORDS and next_line and words <= words_by_line.get(next_line, set()):
            yield Finding.of("clean-code/redundant-comment", Location(path, comment.line), "rename or delete instead")


def _identifier_words_by_line(lexed: Lexed) -> dict[int, set[str]]:
    words: dict[int, set[str]] = {}
    for token in lexed.tokens:
        words.setdefault(token.line, set()).update(_words(token.text))
    return words


def _words(text: str) -> set[str]:
    return {word.lower().removesuffix("s") for word in WORD.findall(text)}
