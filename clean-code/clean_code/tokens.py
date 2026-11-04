from dataclasses import dataclass, field

NO_GAP = ""
SPACE = " "
NEWLINE = "\n"


class LexError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    text: str
    line: int
    gap: str = NO_GAP
    is_docstring: bool = False


@dataclass(frozen=True)
class Comment:
    line: int
    text: str


@dataclass(frozen=True)
class Parameter:
    name: str
    is_boolean: bool


@dataclass(frozen=True)
class Function:
    name: str
    start: int
    end: int
    parameters: tuple[Parameter, ...] = ()
    is_constructor: bool = False

    @property
    def length(self) -> int:
        return self.end - self.start + 1


@dataclass(frozen=True)
class GapRule:
    """How whitespace between two tokens affects meaning in a language."""

    newline_matters: bool
    glue_matters: bool


@dataclass
class Lexed:
    gap_rule: GapRule
    tokens: list[Token] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    functions: list[Function] = field(default_factory=list)


OPERATOR_CHARACTERS = frozenset("+-*/%&|^!=<>?:.~")


def _char_class(char: str) -> str:
    if char.isalnum() or char in "_@$":
        return "word"
    return "operator" if char in OPERATOR_CHARACTERS else "separator"


def _glues(left: str, right: str) -> bool:
    """Two words, or two operator characters, would read as one token if the gap between them went."""
    left_class = _char_class(left[-1])
    return left_class != "separator" and left_class == _char_class(right[0])


def _significant_gap(rule: GapRule, previous: Token | None, token: Token) -> str:
    if previous is None:
        return NO_GAP
    if token.gap == NEWLINE and rule.newline_matters:
        return NEWLINE
    if token.gap and rule.glue_matters and _glues(previous.text, token.text):
        return SPACE
    return NO_GAP


def code_stream(lexed: Lexed, tokens: list[Token] | None = None) -> list[tuple[str, str]]:
    """Token texts with only the whitespace that can change meaning: the form two sides are compared in."""
    chosen = lexed.tokens if tokens is None else tokens
    stream, previous = [], None
    for token in chosen:
        stream.append((token.text, _significant_gap(lexed.gap_rule, previous, token)))
        previous = token
    return stream
