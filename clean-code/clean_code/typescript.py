import json
import subprocess
from pathlib import Path

from .tokens import Comment, Function, GapRule, Lexed, LexError, Parameter, Token

TS_LEXER = Path(__file__).resolve().parent.parent / "ts_lexer.cjs"
TYPESCRIPT_GAPS = GapRule(newline_matters=True, glue_matters=False)


def lex_typescript_files(texts: dict[str, str]) -> dict[str, Lexed | LexError]:
    """Lexes TypeScript and JavaScript with the TypeScript parser in one node process."""
    if not texts:
        return {}
    payload = json.dumps([{"path": path, "text": text} for path, text in texts.items()])
    try:
        done = subprocess.run(["node", str(TS_LEXER)], input=payload, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return dict.fromkeys(texts, LexError("node is not installed"))
    if done.returncode:
        return dict.fromkeys(texts, LexError(f"TypeScript lexer failed: {done.stderr.strip()[:300]}"))
    return {path: _to_lexed(result) for path, result in json.loads(done.stdout).items()}


def _to_lexed(result: dict) -> Lexed | LexError:
    if result["error"]:
        return LexError(f"TypeScript does not parse: {result['error']}")
    return Lexed(
        TYPESCRIPT_GAPS,
        tokens=[Token(text, line, gap) for text, line, gap in result["tokens"]],
        comments=[Comment(line, text) for line, text in result["comments"]],
        functions=[_function(description) for description in result["functions"]],
    )


def _function(description: list) -> Function:
    name, start, end, parameters, is_constructor = description
    described = tuple(Parameter(*parameter) for parameter in parameters)
    return Function(name, start, end, described, is_constructor)
