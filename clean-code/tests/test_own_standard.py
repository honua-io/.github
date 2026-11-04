import ast
import unittest
from pathlib import Path

TOOL_DIRECTORY = Path(__file__).resolve().parents[1]
PRODUCTION_SOURCES = sorted([*TOOL_DIRECTORY.glob("clean_code/**/*.py"), *TOOL_DIRECTORY.glob("*.py")])
MAX_ARGUMENTS = 3
MAX_FUNCTION_LINES = 40
MAX_FILE_LINES = 400


def functions(path: Path) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(path.read_text())
    return [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


def argument_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    arguments = function.args
    names = [argument.arg for argument in arguments.posonlyargs + arguments.args + arguments.kwonlyargs]
    return [name for name in names if name not in {"self", "cls"}]


class OwnStandard(unittest.TestCase):
    """The tool keeps the review rubric's budgets, stricter than the thresholds it enforces on others."""

    def test_functions_take_at_most_three_arguments(self):
        wide = [f"{path.name}:{function.name}" for path in PRODUCTION_SOURCES for function in functions(path)
                if len(argument_names(function)) > MAX_ARGUMENTS]
        self.assertEqual(wide, [])

    def test_functions_and_files_stay_small(self):
        long_functions = [f"{path.name}:{function.name}" for path in PRODUCTION_SOURCES for function in functions(path)
                          if function.end_lineno - function.lineno + 1 > MAX_FUNCTION_LINES]
        long_files = [path.name for path in PRODUCTION_SOURCES if len(path.read_text().splitlines()) > MAX_FILE_LINES]
        self.assertEqual(long_functions + long_files, [])


if __name__ == "__main__":
    unittest.main()
