import ast
import io
import tokenize

from .tokens import Comment, Function, GapRule, Lexed, LexError, Parameter, Token

PYTHON_GAPS = GapRule(newline_matters=False, glue_matters=False)
IGNORED = frozenset({tokenize.NL, tokenize.ENCODING})
STRUCTURAL = frozenset({tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENDMARKER})
DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
Position = tuple[int, int]


def lex_python(text: str) -> Lexed:
    text = text.removeprefix("\ufeff")
    try:
        raw_tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        tree = ast.parse(text)
    except (tokenize.TokenError, SyntaxError) as error:
        raise LexError(f"Python does not parse: {error}") from error
    docstrings = _docstring_spans(tree, text.split("\n"))
    lexed = Lexed(PYTHON_GAPS, functions=_functions(tree))
    for raw in raw_tokens:
        _add_token(lexed, raw, docstrings)
    return lexed


def _add_token(lexed: Lexed, raw: tokenize.TokenInfo, docstrings: list[tuple[Position, Position]]) -> None:
    if raw.type == tokenize.COMMENT:
        lexed.comments.append(Comment(raw.start[0], raw.string))
        return
    if raw.type in IGNORED:
        return
    is_docstring = raw.type == tokenize.STRING and any(start <= raw.start and raw.end <= end for start, end in docstrings)
    if is_docstring:
        lines = raw.string.split("\n")
        lexed.comments.extend(Comment(raw.start[0] + offset, line) for offset, line in enumerate(lines))
    text = tokenize.tok_name[raw.type] if raw.type in STRUCTURAL else raw.string
    lexed.tokens.append(Token(text, raw.start[0], is_docstring=is_docstring))


def _docstring_spans(tree: ast.Module, lines: list[str]) -> list[tuple[Position, Position]]:
    """Docstring expressions as (row, character column) spans, the coordinates tokenize reports."""
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, DOCSTRING_OWNERS) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            start = (first.lineno, _character_column(lines, first.lineno, first.col_offset))
            spans.append((start, (first.end_lineno, _character_column(lines, first.end_lineno, first.end_col_offset))))
    return spans


def _character_column(lines: list[str], row: int, byte_offset: int) -> int:
    """ast columns count UTF-8 bytes; tokenize columns count characters. Rows end only at LF, as both see them."""
    return len(lines[row - 1].encode("utf-8")[:byte_offset].decode("utf-8"))


def _functions(tree: ast.Module) -> list[Function]:
    functions = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = f"{prefix}{getattr(child, 'name', '')}"
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(Function(name, child.lineno, child.end_lineno, _parameters(child.args)))
            is_scope = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            visit(child, f"{name}." if is_scope else prefix)

    visit(tree, "")
    return functions


def _parameters(arguments: ast.arguments) -> tuple[Parameter, ...]:
    """Named parameters other than self/cls; boolean when annotated `bool` or defaulting to True/False."""
    positional = arguments.posonlyargs + arguments.args
    defaults = [None] * (len(positional) - len(arguments.defaults)) + arguments.defaults
    pairs = list(zip(positional, defaults)) + list(zip(arguments.kwonlyargs, arguments.kw_defaults))
    named = [(argument, default) for argument, default in pairs if argument.arg not in {"self", "cls"}]
    return tuple(Parameter(argument.arg, _is_boolean(argument, default)) for argument, default in named)


def _is_boolean(argument: ast.arg, default: ast.expr | None) -> bool:
    """Annotated `bool` (also as a quoted forward reference) or defaulting to True/False."""
    annotation = argument.annotation
    annotated = (isinstance(annotation, ast.Name) and annotation.id == "bool") or (
        isinstance(annotation, ast.Constant) and annotation.value == "bool")
    return annotated or (isinstance(default, ast.Constant) and isinstance(default.value, bool))
