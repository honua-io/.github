import re

from .scanner import Scanner, StringStyle
from .tokens import GapRule, LexError

CSHARP_REGULAR = StringStyle()
CSHARP_INTERPOLATED = StringStyle(hole_openers=("{",), escaped_holes=("{{",))
CSHARP_VERBATIM = StringStyle(escapes=False, doubled_quote_escapes=True, multiline=True)
CSHARP_VERBATIM_INTERPOLATED = StringStyle(
    escapes=False, doubled_quote_escapes=True, multiline=True, hole_openers=("{",), escaped_holes=("{{",)
)
HCL_TEMPLATE = StringStyle(hole_openers=("${", "%{"), escaped_holes=("$${", "%%{"))
SHELL_SINGLE = StringStyle(quote="'", escapes=False, multiline=True)
SHELL_DOUBLE = StringStyle(multiline=True)

RAW_STRING = re.compile(r'(\$*)("{3,})')
BRACE_RUN = re.compile(r"\{+")
CSHARP_LINE_TERMINATOR = re.compile(r"\r\n|[\r\n\u0085\u2028\u2029]")
STRING_PREFIX = re.compile(r'(\$*)(@?)(\$*)"')
CHAR_LITERAL = re.compile(r"'(?:\\[^'\n]{1,9}|[^\\'\n])'")
BACKTICK_STRING = re.compile(r"`[^`]*`")
DIRECTIVE_NAME = re.compile(r"#\s*(\w*)")
MESSAGE_DIRECTIVES = frozenset({"region", "endregion", "error", "warning"})
HEREDOC_OPENER = re.compile(r"<<-?([A-Za-z_]\w*)[ \t]*\r?\n")


def _before_unquoted_comment(directive: str) -> str:
    in_quotes = False
    for index, char in enumerate(directive):
        in_quotes = in_quotes != (char == '"')
        if not in_quotes and directive.startswith("//", index):
            return directive[:index]
    return directive


def _csharp_string_style(prefix: re.Match) -> StringStyle:
    interpolated = "$" in prefix.group(1) + prefix.group(3)
    if prefix.group(2):
        return CSHARP_VERBATIM_INTERPOLATED if interpolated else CSHARP_VERBATIM
    return CSHARP_INTERPOLATED if interpolated else CSHARP_REGULAR


class CSharpScanner(Scanner):
    """C# lexer; also good enough to find comments in other C-family languages."""

    line_terminator = CSHARP_LINE_TERMINATOR

    def scan_token(self) -> None:
        if self.text[self.pos] == "#" and self.at_line_start():
            return self.scan_directive()
        super().scan_token()

    def scan_directive(self) -> None:
        """Emits the directive up to an unquoted '//'; the comment after it is lexed as one."""
        directive = self.text[self.pos:self.line_end()]
        name = DIRECTIVE_NAME.match(directive).group(1)
        code = directive if name in MESSAGE_DIRECTIVES else _before_unquoted_comment(directive)
        self.emit(self.pos + len(code.rstrip()))

    def literal_end(self) -> int | None:
        return self.raw_string_end() or self.quoted_string_end() or self.char_literal_end()

    def raw_string_end(self) -> int | None:
        opener = RAW_STRING.match(self.text, self.pos)
        if not opener:
            return None
        dollars, delimiter = len(opener.group(1)), opener.group(2)
        index = opener.end()
        while index < len(self.text):
            if self.text.startswith(delimiter, index):
                return index + len(delimiter)
            opens_hole = dollars and self.text.startswith("{" * dollars, index)
            index = self.raw_hole_end(index, dollars) if opens_hole else index + 1
        raise LexError(f"unterminated raw string at line {self.line}")

    def raw_hole_end(self, index: int, dollars: int) -> int:
        """In a $$\"\"\" string the last `dollars` braces of a run open a hole, closed by as many braces."""
        hole_start = BRACE_RUN.match(self.text, index).end()
        first_close = self.hole_end(hole_start)
        closing = first_close + dollars - 1
        if self.text[first_close - 1:closing] != "}" * dollars:
            raise LexError(f"malformed raw string interpolation at line {self.line}")
        return closing

    def quoted_string_end(self) -> int | None:
        prefix = STRING_PREFIX.match(self.text, self.pos)
        if not prefix:
            return None
        return self.string_end(prefix.end(), _csharp_string_style(prefix))

    def char_literal_end(self) -> int | None:
        literal = CHAR_LITERAL.match(self.text, self.pos) or BACKTICK_STRING.match(self.text, self.pos)
        return literal.end() if literal else None


class HclScanner(Scanner):
    """Terraform and HCL: '#' and '//' comments, template strings and heredocs; newlines separate attributes."""

    gap_rule = GapRule(newline_matters=True, glue_matters=True)
    line_comment_markers = ("#", "//")
    word_pattern = re.compile(r"\w[\w-]*")

    def literal_end(self) -> int | None:
        if self.text.startswith('"', self.pos):
            return self.string_end(self.pos + 1, HCL_TEMPLATE)
        return self.heredoc_end()

    def heredoc_end(self) -> int | None:
        opener = HEREDOC_OPENER.match(self.text, self.pos)
        if not opener:
            return None
        closing = re.compile(rf"^[ \t]*{re.escape(opener.group(1))}[ \t]*\r?$", re.MULTILINE)
        close = closing.search(self.text, opener.end())
        if not close:
            raise LexError(f"unterminated heredoc at line {self.line}")
        return close.end()


class ShellScanner(Scanner):
    """Finds shell and PowerShell comments: '#' that starts a word, outside quotes."""

    line_comment_markers = ("#",)
    block_comments = False

    def starts_line_comment(self) -> bool:
        starts_word = self.pos == 0 or self.text[self.pos - 1] in " \t\n;(|&"
        return starts_word and self.text.startswith("#", self.pos)

    def literal_end(self) -> int | None:
        quote = self.text[self.pos]
        styles = {"'": SHELL_SINGLE, '"': SHELL_DOUBLE}
        return self.string_end(self.pos + 1, styles[quote]) if quote in styles else None
