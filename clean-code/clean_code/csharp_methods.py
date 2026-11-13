"""Finds C# methods, constructors and local functions in a token stream, without a compiler."""

from .tokens import Function, Parameter, Token

NOT_A_DECLARATION = frozenset({
    "if", "for", "foreach", "while", "switch", "catch", "using", "lock", "fixed", "return", "new", "nameof", "typeof",
    "sizeof", "default", "when", "throw", "await", "checked", "unchecked", "base", "this", "is", "as", "in", "out",
    "ref", "else", "do", "yield", "case", "stackalloc", "with", "and", "or", "not", "record", "class", "struct",
    "interface", "delegate", "operator", "var", "get", "set", "init", "add", "remove", "where",
})
MODIFIERS = frozenset({
    "public", "private", "protected", "internal", "static", "extern", "unsafe", "file", "partial",
})
PARAMETER_MODIFIERS = frozenset({"this", "ref", "out", "in", "params", "scoped", "readonly"})
BOOLEAN_TYPES = frozenset({"bool", "Boolean"})
OPENERS = {"(": ")", "[": "]", "{": "}", "<": ">"}


def find_methods(tokens: list[Token]) -> list[Function]:
    methods = []
    for index, token in enumerate(tokens):
        if token.text == "(":
            method = _method_at(tokens, index)
            if method:
                methods.append(method)
    return methods


def _method_at(tokens: list[Token], open_paren: int) -> Function | None:
    name_index = _name_index(tokens, open_paren)
    if name_index is None:
        return None
    close_paren = _matching(tokens, open_paren)
    body_end = _body_end(tokens, close_paren + 1) if close_paren else None
    if body_end is None:
        return None
    is_constructor = tokens[name_index - 1].text in MODIFIERS
    parameters = tuple(_parameter(segment) for segment in _split_parameters(tokens[open_paren + 1:close_paren]))
    name = tokens[name_index]
    return Function(name.text, name.line, tokens[body_end].line, parameters, is_constructor)


def _name_index(tokens: list[Token], open_paren: int) -> int | None:
    index = open_paren - 1
    if index > 0 and tokens[index].text == ">":
        index = _matching_backwards(tokens, index) - 1
    if index < 1 or not _is_identifier(tokens[index].text) or tokens[index].text in NOT_A_DECLARATION:
        return None
    previous = tokens[index - 1].text
    declares_type = _is_identifier(previous) or previous in {">", "]", "?", "*"}
    return index if declares_type and previous not in NOT_A_DECLARATION else None


def _body_end(tokens: list[Token], index: int) -> int | None:
    index = _skip_initializer_and_constraints(tokens, index)
    if index >= len(tokens):
        return None
    if tokens[index].text == "{":
        return _matching(tokens, index)
    if tokens[index].text == "=" and index + 1 < len(tokens) and tokens[index + 1].text == ">":
        return _statement_end(tokens, index + 2)
    return None


def _skip_initializer_and_constraints(tokens: list[Token], index: int) -> int:
    while index < len(tokens) and tokens[index].text in {":", "where"}:
        index += 1
        while index < len(tokens) and tokens[index].text not in {"{", "=", ";", "where"}:
            index = (_matching(tokens, index) or index) + 1 if tokens[index].text == "(" else index + 1
    return index


def _statement_end(tokens: list[Token], index: int) -> int | None:
    depth = 0
    for position in range(index, len(tokens)):
        text = tokens[position].text
        depth += (text in "([{") - (text in ")]}")
        if text == ";" and depth == 0:
            return position
    return None


def _matching(tokens: list[Token], open_index: int) -> int | None:
    opener = tokens[open_index].text
    closer, depth = OPENERS[opener], 0
    for position in range(open_index, len(tokens)):
        depth += (tokens[position].text == opener) - (tokens[position].text == closer)
        if depth == 0:
            return position
    return None


def _matching_backwards(tokens: list[Token], close_index: int) -> int:
    depth = 0
    for position in range(close_index, -1, -1):
        depth += (tokens[position].text == ">") - (tokens[position].text == "<")
        if depth == 0:
            return position
    return 0


def _split_parameters(tokens: list[Token]) -> list[list[Token]]:
    segments, current, depth = [], [], 0
    for token in tokens:
        depth += (token.text in "([{<") - (token.text in ")]}>")
        if token.text == "," and depth == 0:
            segments.append(current)
            current = []
        else:
            current.append(token)
    return [segment for segment in segments + [current] if segment]


def _parameter(segment: list[Token]) -> Parameter:
    texts = [token.text for token in _without_attributes(segment) if token.text not in PARAMETER_MODIFIERS]
    declaration = texts[: texts.index("=")] if "=" in texts else texts
    name = next((text for text in reversed(declaration) if _is_identifier(text)), "")
    modifiers = {token.text for token in _without_attributes(segment)}
    return Parameter(name, len(declaration) > 1 and declaration[0] in BOOLEAN_TYPES, "out" in modifiers or ("ref" in modifiers and "readonly" not in modifiers))


def _without_attributes(segment: list[Token]) -> list[Token]:
    if not segment or segment[0].text != "[":
        return segment
    close = _matching(segment, 0)
    return segment[close + 1:] if close is not None else segment


def _is_identifier(text: str) -> bool:
    return text[:1].isalpha() or text[:1] in "_@"
