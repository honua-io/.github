import ast
import io
import tokenize

from .tokens import Comment, Function, GapRule, Lexed, LexError, Token

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
    docstrings = _docstring_spans(tree)
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
    is_docstring = raw.type == tokenize.STRING and any(start <= raw.start < end for start, end in docstrings)
    if is_docstring:
        lines = raw.string.split("\n")
        lexed.comments.extend(Comment(raw.start[0] + offset, line) for offset, line in enumerate(lines))
    text = tokenize.tok_name[raw.type] if raw.type in STRUCTURAL else raw.string
    lexed.tokens.append(Token(text, raw.start[0], is_docstring=is_docstring))


def _docstring_spans(tree: ast.Module) -> list[tuple[Position, Position]]:
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, DOCSTRING_OWNERS) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            spans.append(((first.lineno, first.col_offset), (first.end_lineno, first.end_col_offset)))
    return spans


def _functions(tree: ast.Module) -> list[Function]:
    functions = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = f"{prefix}{getattr(child, 'name', '')}"
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(Function(name, child.lineno, child.end_lineno))
            is_scope = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            visit(child, f"{name}." if is_scope else prefix)

    visit(tree, "")
    return functions
