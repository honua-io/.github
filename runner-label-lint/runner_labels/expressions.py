"""Just enough of the GitHub Actions expression grammar to split `||` / `&&` chains."""

import re

STRING_LITERAL = re.compile(r"^'(?:[^']|'')*'$")
WRAPPED = re.compile(r"^\s*\$\{\{(.*)\}\}\s*$", re.DOTALL)
OPENERS = {"(": ")", "[": "]"}


def unwrap(text):
    """Returns the expression inside a value that is exactly one `${{ ... }}`, else None."""
    match = WRAPPED.match(text)
    if not match or "${{" in match.group(1):
        return None
    return match.group(1).strip()


def implicit_expression(text):
    """`if:` values are expressions with or without the `${{ }}` wrapper."""
    return unwrap(text) if "${{" in text else text.strip()


def split_top_level(expression, operator):
    """Splits on `operator` outside strings and brackets."""
    parts, start, depth, index = [], 0, 0, 0
    while index < len(expression):
        character = expression[index]
        if character == "'":
            index = _end_of_string(expression, index)
            continue
        if character in OPENERS:
            depth += 1
        elif character in OPENERS.values():
            depth -= 1
        elif depth == 0 and expression.startswith(operator, index):
            parts.append(expression[start:index].strip())
            start = index + len(operator)
            index = start
            continue
        index += 1
    parts.append(expression[start:].strip())
    return parts


def _end_of_string(expression, index):
    index += 1
    while index < len(expression):
        if expression[index] != "'":
            index += 1
        elif expression.startswith("''", index):
            index += 2
        else:
            return index + 1
    return index


def strip_parentheses(term):
    term = term.strip()
    while term.startswith("(") and _closing_index(term) == len(term) - 1:
        term = term[1:-1].strip()
    return term


def _closing_index(term):
    depth, index = 0, 0
    while index < len(term):
        if term[index] == "'":
            index = _end_of_string(term, index)
            continue
        depth += {"(": 1, ")": -1}.get(term[index], 0)
        if depth == 0:
            return index
        index += 1
    return -1


def string_value(term):
    """The value of a quoted literal, or None when the term is not one."""
    if STRING_LITERAL.match(term):
        return term[1:-1].replace("''", "'")
    return None


def is_compound(term):
    return len(split_top_level(term, "||")) > 1 or len(split_top_level(term, "&&")) > 1


def compact(term):
    return re.sub(r"\s+", "", strip_parentheses(term))
