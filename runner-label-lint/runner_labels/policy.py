"""Which runner labels are GitHub-hosted, and which expression terms guard against forks."""

from dataclasses import dataclass, field
import re

from .expressions import compact, implicit_expression, split_top_level, string_value, strip_parentheses

HOSTED_LABEL = re.compile(
    r"^(?:ubuntu-(?:latest|slim|\d{2}\.\d{2}(?:-arm)?)"
    r"|windows-(?:latest|\d{4}|11-arm)"
    r"|macos-(?:latest|\d{2})(?:-large|-xlarge|-intel)?)$")
DEFAULT_DENIED = frozenset({"self-hosted", "honua-light"})

PULL_REQUEST_EVENTS = frozenset({"pull_request", "pull_request_target", "pull_request_review",
                                 "pull_request_review_comment"})
WORKFLOW_RUN = "workflow_run"
# Anyone can trigger these on a public repository and no context field says whether the actor is
# outside the organization, so no expression guards them: a self-hosted choice must exclude the
# event by name (`github.event_name != 'issue_comment'`).
UNTRUSTED_ACTOR_EVENTS = frozenset({"issue_comment", "issues", "discussion", "discussion_comment"})
FORK_REACHABLE_EVENTS = PULL_REQUEST_EVENTS | UNTRUSTED_ACTOR_EVENTS | {WORKFLOW_RUN}
EVENT_NAME = "github.event_name"

PULL_REQUEST_GUARD = "pull_request"
WORKFLOW_RUN_GUARD = "workflow_run"
EVENT_EXCLUSION_PREFIX = "exclude:"
_SAME_REPOSITORY = {
    PULL_REQUEST_GUARD: "github.event.pull_request.head.repo.full_name",
    WORKFLOW_RUN_GUARD: "github.event.workflow_run.head_repository.full_name",
}
_GUARD_TEXT = {
    PULL_REQUEST_GUARD: "(!github.event.pull_request || github.event.pull_request.head.repo.full_name"
                        " == github.repository)",
    WORKFLOW_RUN_GUARD: "(!github.event.workflow_run || github.event.workflow_run.head_repository.full_name"
                        " == github.repository)",
}


def guard_text(kind):
    if kind.startswith(EVENT_EXCLUSION_PREFIX):
        return f"github.event_name != '{kind.removeprefix(EVENT_EXCLUSION_PREFIX)}'"
    return _GUARD_TEXT[kind]


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
    sides = (_SAME_REPOSITORY[kind], "github.repository")
    equalities = {f"{left}=={right}" for left, right in (sides, sides[::-1])}
    absent = f"!github.event.{kind}"
    return equalities | {form for equality in equalities
                         for form in (f"{absent}||{equality}", f"{equality}||{absent}")}


_GUARDS = {kind: _guard_forms(kind) for kind in _SAME_REPOSITORY}


def guards_in(term):
    """The fork guards a single `&&` conjunct establishes."""
    text = compact(term)
    return {kind for kind, forms in _GUARDS.items() if text in forms}


def required_guards(events):
    needed = {f"{EVENT_EXCLUSION_PREFIX}{event}" for event in events & UNTRUSTED_ACTOR_EVENTS}
    if events & PULL_REQUEST_EVENTS:
        needed.add(PULL_REQUEST_GUARD)
    if WORKFLOW_RUN in events:
        needed.add(WORKFLOW_RUN_GUARD)
    return needed


@dataclass(frozen=True)
class Admission:
    """The events a job `if:` still lets through unguarded, and the guards it applies to all of them."""
    events: frozenset
    guards: frozenset


def admit(condition, events):
    """Drops the events a job `if:` excludes or fully guards; an unparsed condition admits everything."""
    if condition is False:
        return Admission(frozenset(), frozenset())
    expression = implicit_expression(condition) if isinstance(condition, str) else None
    if expression is None:
        return Admission(frozenset(events), frozenset())
    guards_by_event = _guards_by_event(expression, events)
    unguarded = {event for event, guards in guards_by_event.items() if not required_guards({event}) <= guards}
    shared = frozenset.intersection(*(guards_by_event[event] for event in unguarded)) if unguarded else frozenset()
    return Admission(frozenset(unguarded), shared)


def _guards_by_event(expression, events):
    """For each event some `||` branch admits, the guards every admitting branch applies."""
    if whole := guards_in(expression):
        return {event: frozenset(whole) for event in events}
    admitted = {}
    for branch in split_top_level(expression, "||"):
        remaining, guards = set(events), set()
        for conjunct in split_top_level(strip_parentheses(branch), "&&"):
            remaining = narrow_events(conjunct, remaining)
            guards |= guards_in(conjunct)
        for event in remaining:
            admitted[event] = admitted.get(event, frozenset(guards)) & guards
    return admitted


def narrow_events(conjunct, events):
    """The events for which an `&&` conjunct can be true; event names compare case-insensitively."""
    conjunct = compact(conjunct)
    if conjunct == "false":
        return set()
    for operator in ("==", "!="):
        left, found, right = conjunct.partition(operator)
        if not found or EVENT_NAME not in (left, right):
            continue
        other = string_value(right if left == EVENT_NAME else left)
        if other is not None:
            return {event for event in events if (event == other.lower()) == (operator == "==")}
    return set(events)
