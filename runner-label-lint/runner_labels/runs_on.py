"""Decides whether a job's runs-on could resolve to a self-hosted runner for a fork-originated event."""

from dataclasses import dataclass, replace
import re

from .expressions import is_compound, split_top_level, string_value, strip_parentheses, unwrap
from .policy import LabelPolicy, admit, guard_text, guards_in, narrow_events, required_guards
from .workflows import calls_other_repository

MAX_RESOLUTION_DEPTH = 4
MATRIX_REFERENCE = re.compile(r"^matrix\.([A-Za-z_][\w-]*)$")
INPUT_REFERENCE = re.compile(r"^inputs\.([A-Za-z_][\w-]*)$")
RUNNER_ARGUMENT = re.compile(r"runner|runs[-_]?on|label", re.IGNORECASE)
HOSTED_FALLBACK = "ubuntu-latest"

LABEL_HINT = (f"use a GitHub-hosted label such as {HOSTED_FALLBACK}, or choose the self-hosted label"
              " through the fork-guarded expression")
GROUP_HINT = "choose the runner group through the fork-guarded expression, or skip the job for forks in its if:"
FALLBACK_HINT = f"end the expression with || '{HOSTED_FALLBACK}' so fork events get a GitHub-hosted runner"
TEMPLATE_HINT = "make runs-on a single ${{ }} expression or a literal label"


@dataclass(frozen=True)
class Problem:
    reason: str
    hint: str


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    message: str
    hint: str

    def __str__(self):
        return f"{self.path}:{self.line}: {self.message}. Fix: {self.hint}."


@dataclass(frozen=True)
class RunnerSite:
    """A runs-on value, or a runner argument to another repository's workflow, and where it is."""
    name: str
    line: int
    value: object


@dataclass(frozen=True)
class JobContext:
    workflow: object
    job: dict
    events: frozenset
    labels: LabelPolicy
    depth: int = 0

    @property
    def required(self):
        return required_guards(self.events)


def check_workflow(workflow, labels):
    findings = []
    for job_id, job in workflow.jobs():
        if not isinstance(job, dict):
            continue
        if "runs-on" in job:
            site = RunnerSite(f"jobs.{job_id}.runs-on", job.line("runs-on"), job["runs-on"])
            findings += _check_value(workflow, job, site, labels)
        elif calls_other_repository(job):
            findings += _check_remote_call(workflow, job_id, job, labels)
    return findings


def _check_remote_call(workflow, job_id, job, labels):
    """Another repository's workflow is not linted here, so check the runner arguments this job passes it."""
    arguments = job.get("with")
    if not isinstance(arguments, dict):
        return []
    sites = [RunnerSite(f"jobs.{job_id}.with.{key}", arguments.line(key), value)
             for key, value in arguments.items() if isinstance(key, str) and RUNNER_ARGUMENT.search(key)]
    return [finding for site in sites for finding in _check_value(workflow, job, site, labels)]


def _check_value(workflow, job, site, labels):
    admission = admit(job.get("if"), workflow.events)
    if not admission.events:
        return []
    context = JobContext(workflow, job, admission.events, labels)
    problems = runs_on_problems(site.value, context, admission.guards)
    if not problems:
        return []
    reasons = "; ".join(dict.fromkeys(problem.reason for problem in problems))
    hints = "; ".join(dict.fromkeys(problem.hint for problem in problems))
    return [Finding(workflow.path, site.line, f"{site.name}: {reasons}", hints)]


def runs_on_problems(value, context, guards):
    if isinstance(value, list):
        return [problem for item in value for problem in runs_on_problems(item, context, guards)]
    if isinstance(value, dict):
        return [] if context.required <= guards else [Problem("a runner group is reachable from fork-reachable events", GROUP_HINT)]
    if not isinstance(value, str):
        return [Problem("runs-on is not a label, list or group", TEMPLATE_HINT)]
    if "${{" not in value:
        return _label_problems(value, context)
    expression = unwrap(value)
    if expression is None:
        return [Problem("runs-on mixes literal text with an expression", TEMPLATE_HINT)]
    return _expression_problems(expression, context, guards)


def _label_problems(label, context):
    if context.labels.is_hosted(label):
        return []
    return [Problem(f"label '{_printable(label)}' is not a GitHub-hosted runner", LABEL_HINT)]


def _expression_problems(expression, context, guards):
    alternatives = split_top_level(expression, "||")
    problems = [problem for alternative in alternatives
                for problem in _alternative_problems(alternative, context, guards)]
    if not problems and not _is_hosted_fallback(alternatives[-1], context):
        problems.append(Problem("the expression has no GitHub-hosted fallback", FALLBACK_HINT))
    return problems


def _alternative_problems(alternative, context, guards):
    conjuncts = split_top_level(alternative, "&&")
    events = set(context.events)
    for conjunct in conjuncts[:-1]:
        events = narrow_events(conjunct, events)
    established = set(guards).union(*(guards_in(conjunct) for conjunct in conjuncts[:-1]))
    return _value_problems(conjuncts[-1], replace(context, events=frozenset(events)), frozenset(established))


def _is_hosted_fallback(alternative, context):
    conjuncts = split_top_level(alternative, "&&")
    return len(conjuncts) == 1 and not _value_problems(conjuncts[0], context, frozenset())


def _value_problems(term, context, guards):
    term = strip_parentheses(term)
    if is_compound(term):
        return [problem for alternative in split_top_level(term, "||")
                for problem in _alternative_problems(alternative, context, guards)]
    if context.required <= guards:
        return []
    literal = string_value(term)
    if literal is not None:
        return _label_problems(literal, context)
    candidates = _resolve(term, context)
    if candidates is None:
        missing = " && ".join(guard_text(kind) for kind in sorted(context.required - guards))
        return [Problem(f"'{_printable(term)}' can choose a self-hosted runner for fork-reachable events without a guard",
                        f"AND that choice with {missing} and end with || '{HOSTED_FALLBACK}'")]
    return [problem for value, value_context in candidates
            for problem in runs_on_problems(value, value_context, guards)]


def _resolve(term, context):
    """Every runs-on value a matrix or input reference can take, each with its context; None if unknown."""
    if context.depth >= MAX_RESOLUTION_DEPTH:
        return None
    deeper = replace(context, depth=context.depth + 1)
    if match := MATRIX_REFERENCE.match(term):
        values = _matrix_values(context.job, match.group(1))
        return None if values is None else [(value, deeper) for value in values]
    if match := INPUT_REFERENCE.match(term):
        return _input_values(context, match.group(1))
    return None


def _matrix_values(job, name):
    strategy = job.get("strategy")
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    if not isinstance(matrix, dict):
        return None
    base = matrix.get(name, [])
    if not isinstance(base, list):
        return None
    include = matrix.get("include", [])
    if not isinstance(include, list):
        return None
    values = base + [entry[name] for entry in include if isinstance(entry, dict) and name in entry]
    return values or None


def _input_values(context, name):
    candidates = []
    for call in context.workflow.calls:
        caller_context = JobContext(call.caller, call.job, call.admission.events, context.labels, context.depth + 1)
        if caller_context.required <= call.admission.guards:
            continue
        arguments = call.job.get("with")
        value = arguments.get(name) if isinstance(arguments, dict) and name in arguments else None
        value = context.workflow.input_default(name) if value is None else value
        if value is not None:
            candidates.append((value, caller_context))
    return candidates


def _printable(text):
    return "".join(character if character.isprintable() else "?" for character in str(text))[:120]
