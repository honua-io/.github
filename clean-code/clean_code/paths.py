import re
from functools import lru_cache

GENERATED_OR_VENDORED = (
    "**/node_modules/**", "**/dist/**", "**/build/**", "**/vendor/**", "**/third_party/**", "**/wwwroot/lib/**",
    "**/*.min.*", "**/*.bundle.*", "**/assets/*-????????.{js,mjs,cjs,css}", "**/*.d.ts", "**/*.g.cs", "**/*.g.i.cs", "**/*.Designer.cs", "**/*.generated.*",
    "**/generated/**", "**/Generated/**", "**/Migrations/**", "**/*_pb2.py", "**/*_pb2_grpc.py", "**/*.pb.go",
    "**/__snapshots__/**",
)
TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|e2e|spec)/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$"
    r"|\.(test|spec)\.[^/]+$|Tests?\.cs$|(^|/)[^/]*\.Tests?/"
)
GLOB_PARTS = re.compile(r"\*\*/|\*\*|\*|\?|\{[^}]*\}|[^*?{]+")


def _glob_part_pattern(part: str) -> str:
    special = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}
    if part in special:
        return special[part]
    if part.startswith("{"):
        return "(?:" + "|".join(re.escape(choice) for choice in part[1:-1].split(",")) + ")"
    return re.escape(part)


@lru_cache(maxsize=None)
def glob_pattern(glob: str) -> re.Pattern:
    """Compiles a gitignore-style glob: '**/' spans directories, '*' stays within one."""
    return re.compile("".join(_glob_part_pattern(part) for part in GLOB_PARTS.findall(glob)) + "$")


def matches_any(path: str, globs: tuple[str, ...]) -> bool:
    return any(glob_pattern(glob).match(path) for glob in globs)


def is_test_path(path: str) -> bool:
    return bool(TEST_PATH.search(path))

