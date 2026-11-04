import json
import re
from dataclasses import dataclass
from pathlib import Path

BUDGETS_FILE = Path(__file__).resolve().parent.parent / "budgets.json"


@dataclass(frozen=True)
class Budgets:
    """Thresholds shared with eslint.config.mjs, which reads the same budgets.json."""

    function_lines: int
    function_growth_lines: int
    parameters: int
    new_file_lines: int
    large_file_lines: int
    large_file_growth_lines: int
    duplicate_lines: int
    duplicate_tokens: int
    complexity: int
    cognitive_complexity: int
    nesting_depth: int


def _snake_case(name: str) -> str:
    return re.sub(r"[A-Z]", lambda capital: "_" + capital.group().lower(), name)


BUDGETS = Budgets(**{_snake_case(key): value for key, value in json.loads(BUDGETS_FILE.read_text()).items()})
