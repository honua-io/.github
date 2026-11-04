import re

from dataclasses import dataclass

from .tokens import NEWLINE, NO_GAP, SPACE, Comment, GapRule, Lexed, LexError, Token

WHITESPACE = re.compile(r"[ \t\r\n\f\v ﻿]+")
WORD = re.compile(r"[\w@]+")


@dataclass(frozen=True)
class StringStyle:
    quote: str = '"'
    escapes: bool = True
    doubled_quote_escapes: bool = False
    multiline: bool = False
    hole_openers: tuple[str, ...] = ()
    escaped_holes: tuple[str, ...] = ()


class Scanner:
    """Splits source into code tokens and comments; string literals stay whole tokens."""

    gap_rule = GapRule(newline_matters=False, glue_matters=True)
    line_comment_markers: tuple[str, ...] = ("//",)
    block_comments = True
    word_pattern = WORD

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.line = 1
        self.gap = NO_GAP
        self.lexed = Lexed(self.gap_rule)

    def lex(self) -> Lexed:
        while self.skip_trivia():
            self.scan_token()
        return self.lexed

    def skip_trivia(self) -> bool:
        while self.pos < len(self.text):
            if not (self.skip_whitespace() or self.skip_line_comment() or self.skip_block_comment()):
                return True
        return False

    def skip_whitespace(self) -> bool:
        match = WHITESPACE.match(self.text, self.pos)
        if not match:
            return False
        self.widen_gap(NEWLINE if "\n" in match.group() else SPACE)
        self.advance_to(match.end())
        return True

    def skip_line_comment(self) -> bool:
        if not self.starts_line_comment():
            return False
        end = self.text.find("\n", self.pos)
        end = len(self.text) if end < 0 else end
        self.add_comment(end)
        self.widen_gap(SPACE)
        return True

    def starts_line_comment(self) -> bool:
        return any(self.text.startswith(marker, self.pos) for marker in self.line_comment_markers)

    def skip_block_comment(self) -> bool:
        if not (self.block_comments and self.text.startswith("/*", self.pos)):
            return False
        end = self.text.find("*/", self.pos + 2)
        if end < 0:
            raise LexError(f"unterminated block comment at line {self.line}")
        self.widen_gap(NEWLINE if "\n" in self.text[self.pos:end] else SPACE)
        self.add_comment(end + 2)
        return True

    def add_comment(self, end: int) -> None:
        for offset, text in enumerate(self.text[self.pos:end].split("\n")):
            self.lexed.comments.append(Comment(self.line + offset, text))
        self.advance_to(end)

    def widen_gap(self, gap: str) -> None:
        if self.gap != NEWLINE:
            self.gap = gap

    def advance_to(self, end: int) -> None:
        self.line += self.text.count("\n", self.pos, end)
        self.pos = end

    def emit(self, end: int, text: str | None = None) -> None:
        start_line = self.line
        token_text = self.text[self.pos:end] if text is None else text
        self.advance_to(end)
        self.lexed.tokens.append(Token(token_text, start_line, self.gap))
        self.gap = NO_GAP

    def scan_token(self) -> None:
        end = self.literal_end()
        if end is not None:
            return self.emit(end)
        word = self.word_pattern.match(self.text, self.pos)
        self.emit(word.end() if word else self.pos + 1)

    def literal_end(self) -> int | None:
        return None

    def at_line_start(self) -> bool:
        line_start = self.text.rfind("\n", 0, self.pos) + 1
        return not self.text[line_start:self.pos].strip()

    def string_end(self, start: int, style: "StringStyle") -> int:
        """End of a string literal whose opening quote is just before start."""
        index = start
        while index < len(self.text):
            index, closed = self.string_step(index, style)
            if closed:
                return index
        raise LexError(f"unterminated string at line {self.line}")

    def string_step(self, index: int, style: "StringStyle") -> tuple[int, bool]:
        text = self.text
        if style.escapes and text[index] == "\\":
            return index + 2, False
        if text.startswith(style.quote * 2, index) and style.doubled_quote_escapes:
            return index + 2, False
        if text[index] == style.quote:
            return index + 1, True
        escaped_hole = next((marker for marker in style.escaped_holes if text.startswith(marker, index)), None)
        if escaped_hole:
            return index + len(escaped_hole), False
        hole = next((marker for marker in style.hole_openers if text.startswith(marker, index)), None)
        if hole:
            return self.hole_end(index + len(hole)), False
        if text[index] == "\n" and not style.multiline:
            raise LexError(f"newline in string at line {self.line}")
        return index + 1, False

    def hole_end(self, start: int) -> int:
        """End of an interpolation hole whose opening brace is just before start."""
        saved = (self.pos, self.line, self.gap, len(self.lexed.tokens))
        self.advance_to(start)
        depth = 0
        while self.skip_trivia():
            char = self.text[self.pos]
            if char == "}" and depth == 0:
                end = self.pos + 1
                self.pos, self.line, self.gap, token_count = saved
                del self.lexed.tokens[token_count:]
                return end
            depth += {"{": 1, "}": -1}.get(char, 0)
            self.scan_token()
        raise LexError(f"unterminated interpolation at line {saved[1]}")
