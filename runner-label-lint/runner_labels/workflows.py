"""Loads workflow files as data and works out which jobs fork-originated events can reach."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .policy import FORK_REACHABLE_EVENTS, Admission, admit

WORKFLOW_DIRECTORY = Path(".github/workflows")
LOCAL_CALL_PREFIX = "./"
MAX_WORKFLOW_BYTES = 1 << 20


class LineMapping(dict):
    """A mapping that remembers the 1-based source line of each key."""

    def __init__(self):
        super().__init__()
        self.lines = {}

    def line(self, key, default=0):
        return self.lines.get(key, default)


class _LineLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node):
    loader.flatten_mapping(node)
    mapping = LineMapping()
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, (str, int, bool, float)) and key is not None:
            raise yaml.constructor.ConstructorError(None, None, "unhashable key", key_node.start_mark)
        mapping[key] = loader.construct_object(value_node, deep=True)
        mapping.lines[key] = key_node.start_mark.line + 1
    return mapping


_LineLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


class WorkflowError(Exception):
    def __init__(self, path, message, line=1):
        super().__init__(message)
        self.path = path
        self.line = line


@dataclass
class Call:
    """A PR-reachable job in `caller` that runs a local reusable workflow."""
    caller: "Workflow"
    job: LineMapping
    admission: Admission


@dataclass
class Workflow:
    path: str
    document: LineMapping
    events: set = field(default_factory=set)
    calls: list = field(default_factory=list)

    def jobs(self):
        jobs = self.document.get("jobs")
        return jobs.items() if isinstance(jobs, dict) else ()

    def input_default(self, name):
        triggers = _triggers(self.document)
        call = triggers.get("workflow_call") if isinstance(triggers, dict) else None
        inputs = call.get("inputs") if isinstance(call, dict) else None
        spec = inputs.get(name) if isinstance(inputs, dict) else None
        return spec.get("default") if isinstance(spec, dict) else None


def load_repository(root):
    """Returns (workflows by repository-relative path, load errors)."""
    directory = Path(root) / WORKFLOW_DIRECTORY
    workflows, errors = {}, []
    if directory.is_dir() and not directory.resolve().is_relative_to(Path(root).resolve()):
        return workflows, [WorkflowError(WORKFLOW_DIRECTORY.as_posix(), "resolves outside the repository")]
    candidates = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml")) if directory.is_dir() else []
    for path in candidates:
        relative = (WORKFLOW_DIRECTORY / path.name).as_posix()
        try:
            workflows[relative] = Workflow(relative, _read(path, relative))
        except WorkflowError as error:
            errors.append(error)
    _propagate_events(workflows)
    return workflows, errors


def _read(path, relative):
    if path.is_symlink() or not path.is_file():
        raise WorkflowError(relative, "not a regular file")
    if path.stat().st_size > MAX_WORKFLOW_BYTES:
        raise WorkflowError(relative, "larger than 1 MiB")
    try:
        document = yaml.load(path.read_bytes(), Loader=_LineLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = mark.line + 1 if mark else 1
        raise WorkflowError(relative, f"not valid YAML ({type(error).__name__})", line) from None
    if not isinstance(document, LineMapping):
        raise WorkflowError(relative, "top level is not a mapping")
    return document


def _triggers(document):
    return document.get("on", document.get(True))


def trigger_events(document):
    triggers = _triggers(document)
    if isinstance(triggers, str):
        triggers = [triggers]
    names = triggers.keys() if isinstance(triggers, dict) else triggers or []
    return {name for name in names if isinstance(name, str)} & FORK_REACHABLE_EVENTS


def local_callee(job):
    uses = job.get("uses") if isinstance(job, dict) else None
    if not isinstance(uses, str) or not uses.startswith(LOCAL_CALL_PREFIX):
        return None
    return uses[len(LOCAL_CALL_PREFIX):].split("@", 1)[0]


def calls_other_repository(job):
    uses = job.get("uses")
    return isinstance(uses, str) and not uses.startswith(LOCAL_CALL_PREFIX) and "/.github/workflows/" in uses


def _propagate_events(workflows):
    for workflow in workflows.values():
        workflow.events = trigger_events(workflow.document)
    pending = [workflow for workflow in workflows.values() if workflow.events]
    while pending:
        caller = pending.pop()
        for _, job in caller.jobs():
            callee = workflows.get(local_callee(job))
            if callee is not None and _record_call(caller, job, callee):
                pending.append(callee)


def _record_call(caller, job, callee):
    """Adds the call when it carries fork-reachable events; True when the callee learned new events."""
    admission = admit(job.get("if"), caller.events)
    if not admission.events:
        return False
    callee.calls = [call for call in callee.calls if call.job is not job] + [Call(caller, job, admission)]
    before = set(callee.events)
    callee.events |= admission.events
    return callee.events != before
