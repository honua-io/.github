"""Which runner labels are GitHub-hosted, and which expression terms guard against forks."""

from dataclasses import dataclass, field
import re

from .expressions import compact, implicit_expression, split_top_level, string_value

HOSTED_LABEL = re.compile(
    r"^(?:ubuntu-(?:latest|slim|\d{2}\.\d{2}(?:-arm)?)"
    r"|windows-(?:latest|\d{4}|11-arm)"
    r"|macos-(?:latest|\d{2})(?:-large|-xlarge|-intel)?)$")
DEFAULT_DENIED = frozenset({"self-hosted", "honua-light"})

PULL_REQUEST_EVENTS = frozenset({"pull_request", "pull_request_target", "pull_request_review",
                                 "pull_request_review_comment"})
WORKFLOW_RUN = "workflow_run"
FORK_REACHABLE_EVENTS = PULL_REQUEST_EVENTS | {WORKFLOW_RUN}
EVENT_NAME = "github.event_name"

PULL_REQUEST_GUARD = "pull_request"
WORKFLOW_RUN_GUARD = "workflow_run"
_SAME_REPOSITORY = {
    PULL_REQUEST_GUARD: "github.event.pull_request.head.repo.full_name",
    WORKFLOW_RUN_GUARD: "github.event.workflow_run.head_repository.full_name",
}
GUARD_TEXT = {
    PULL_REQUEST_GUARD: "(!github.event.pull_request || github.event.pull_request.head.repo.full_name"
                        " == github.repository)",
    WORKFLOW_RUN_GUARD: "(!github.event.workflow_run || github.event.workflow_run.head_repository.full_name"
                        " == github.repository)",
}


@dataclass(frozen=True)
class LabelPolicy:
    allowed: frozenset = field(default_factory=frozenset)
    denied: frozenset = DEFAULT_DENIED

    def is_hosted(self, label):
        label = label.strip().lower()
        if label in self.denied:
            return False
        return label in self.allowed or bool(HOSTED_LABEL.match(label))


def _guard_forms(kind):
    equality = f"{_SAME_REPOSITORY[kind]}==github.repository"
    reverse = f"github.repository=={_SAME_REPOSITORY[kind]}"
    event = f"github.event.{kind}"
    return {equality, reverse, f"!{event}||{equality}", f"!{event}||{reverse}"}


_GUARDS = {kind: _guard_forms(kind) for kind in _SAME_REPOSITORY}


def guards_in(term):
    """The fork guards a single `&&` conjunct establishes."""
    text = compact(term)
    return {kind for kind, forms in _GUARDS.items() if text in forms}


def required_guards(events):
    needed = set()
    if events & PULL_REQUEST_EVENTS:
        needed.add(PULL_REQUEST_GUARD)
    if WORKFLOW_RUN in events:
        needed.add(WORKFLOW_RUN_GUARD)
    return needed


@dataclass(frozen=True)
class Admission:
    """What a job `if:` lets through: the events that can still run it, and guards it already applies."""
    events: frozenset
    guards: frozenset


def admit(condition, events):
    """Narrows `events` by a job `if:` that is a plain `&&` chain; anything else admits everything."""
    if condition is False:
        return Admission(frozenset(), frozenset())
    if not isinstance(condition, str):
        return Admission(frozenset(events), frozenset())
    expression = implicit_expression(condition)
    if expression is None or len(split_top_level(expression, "||")) > 1:
        return Admission(frozenset(events), frozenset())
    remaining, guards = set(events), set()
    for conjunct in split_top_level(expression, "&&"):
        remaining = _narrow(compact(conjunct), remaining)
        guards |= guards_in(conjunct)
    return Admission(frozenset(remaining), frozenset(guards))


def _narrow(conjunct, events):
    if conjunct == "false":
        return set()
    for operator in ("==", "!="):
        left, found, right = conjunct.partition(operator)
        if not found or EVENT_NAME not in (left, right):
            continue
        other = string_value(right if left == EVENT_NAME else left)
        if other is not None:
            return {event for event in events if (event == other) == (operator == "==")}
    return events
