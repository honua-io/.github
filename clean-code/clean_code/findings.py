from dataclasses import dataclass

from .catalog import RULES, Rule, Severity


@dataclass(frozen=True)
class Location:
    path: str
    line: int


@dataclass(frozen=True)
class Finding:
    rule: Rule
    location: Location
    message: str

    @classmethod
    def of(cls, key: str, location: Location, message: str) -> "Finding":
        return cls(RULES[key], location, message)

    @property
    def blocking(self) -> bool:
        return self.rule.severity is Severity.BLOCK
