"""Track direct collection mutations without confusing local copies with caller inputs."""
import ast

MUTATORS = frozenset({
    'append', 'extend', 'insert', 'add', 'update', 'setdefault', 'sort', 'clear',
    'reverse', 'pop', 'popitem', 'remove', 'discard', 'difference_update',
    'intersection_update', 'symmetric_difference_update',
})
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def output_names(function):
    arguments = function.args
    parameters = arguments.posonlyargs + arguments.args + arguments.kwonlyargs
    visitor = Mutations({argument.arg: {argument.arg} for argument in parameters})
    visitor.statements(function.body)
    return visitor.outputs


def merge_bindings(endings):
    merged = {}
    for ending in endings:
        for name, values in ending.items():
            merged.setdefault(name, set()).update(values)
    return merged


class Mutations(ast.NodeVisitor):
    def __init__(self, bindings):
        self.bindings = bindings
        self.outputs = set()
        self.exits = []

    def statements(self, statements):
        for statement in statements:
            if self.visit(statement) is False:
                return False
        return True

    def visit(self, node):
        if isinstance(node, SCOPES):
            return
        if isinstance(node, COMPREHENSIONS):
            self.comprehension(node)
            return
        result = super().visit(node)
        if self.exits and isinstance(node, (ast.Call, ast.Attribute, ast.Subscript,
                                           ast.BinOp, ast.Compare, ast.Await)):
            self.exits[-1].append((merge_bindings([self.bindings]), 'throw'))
        return result

    def aliases(self, node):
        if isinstance(node, ast.NamedExpr):
            return self.aliases(node.target)
        return self.bindings.get(node.id, set()).copy() if isinstance(node, ast.Name) else set()

    def bind(self, target, aliases):
        if isinstance(target, ast.Name):
            self.bindings[target.id] = aliases
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self.bind(element, set())

    def visit_Assign(self, node):
        self.visit(node.value)
        aliases = self.aliases(node.value)
        for target in node.targets:
            self.visit(target)
            self.bind(target, aliases.copy())

    def visit_AnnAssign(self, node):
        if node.value:
            self.visit(node.value)
            self.visit(node.target)
            self.bind(node.target, self.aliases(node.value))

    def visit_NamedExpr(self, node):
        self.visit(node.value)
        self.bind(node.target, self.aliases(node.value))

    def visit_Call(self, node):
        self.visit(node.func)
        receiver = (self.aliases(node.func.value)
                    if isinstance(node.func, ast.Attribute) and node.func.attr in MUTATORS else set())
        self.statements([*node.args, *node.keywords])
        self.outputs.update(receiver)

    def visit_Subscript(self, node):
        self.visit(node.value)
        receiver = self.aliases(node.value)
        self.visit(node.slice)
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.outputs.update(receiver)

    def branches(self, paths):
        initial = {name: values.copy() for name, values in self.bindings.items()}
        endings = []
        for path in paths:
            self.bindings = {name: values.copy() for name, values in initial.items()}
            if self.statements(path):
                endings.append(self.bindings)
        self.bindings = {}
        for ending in endings:
            for name, values in ending.items():
                self.bindings.setdefault(name, set()).update(values)
        return bool(endings)

    def visit_BoolOp(self, node):
        self.visit(node.values[0])
        for value in node.values[1:]:
            self.branches([[], [value]])

    def visit_Compare(self, node):
        self.visit(node.left)
        self.visit(node.comparators[0])
        for comparator in node.comparators[1:]:
            self.branches([[], [comparator]])

    def visit_IfExp(self, node):
        self.visit(node.test)
        self.branches([[node.body], [node.orelse]])

    def captured_statements(self, body):
        self.exits.append([])
        normal = self.statements(body)
        exits = self.exits.pop()
        return normal, exits

    def exception_paths(self, node):
        normal, exits = self.captured_statements(node.body)
        exceptional = merge_bindings([bindings for bindings, kind in exits if kind == 'throw'])
        paths = [(bindings, False, kind) for bindings, kind in exits
                 if kind != 'throw' or not node.handlers or all(handler.type for handler in node.handlers)]
        if normal:
            normal, other_exits = self.captured_statements(node.orelse)
            paths.extend((bindings, False, kind) for bindings, kind in other_exits)
            if normal:
                paths.append((self.bindings, True, 'normal'))
        for handler in node.handlers if exceptional else []:
            self.bindings = merge_bindings([exceptional])
            if handler.name:
                self.bindings[handler.name] = set()
            normal, handler_exits = self.captured_statements(handler.body)
            if normal:
                paths.append((self.bindings, True, 'normal'))
            paths.extend((bindings, False, kind) for bindings, kind in handler_exits)
        return paths

    def visit_Try(self, node):
        endings = []
        for bindings, normal, kind in self.exception_paths(node):
            self.bindings = merge_bindings([bindings])
            final_normal, final_exits = self.captured_statements(node.finalbody)
            if self.exits:
                self.exits[-1].extend(final_exits)
                if final_normal and not normal:
                    self.exits[-1].append((merge_bindings([self.bindings]), kind))
            if normal and final_normal:
                endings.append(self.bindings)
        self.bindings = merge_bindings(endings)
        return bool(endings)

    visit_TryStar = visit_Try

    def visit_If(self, node):
        self.visit(node.test)
        return self.branches([node.body, node.orelse])

    def visit_Match(self, node):
        self.visit(node.subject)
        subject_aliases = self.aliases(node.subject)
        remaining = merge_bindings([self.bindings])
        endings = []
        for case in node.cases:
            self.bindings = merge_bindings([remaining])
            self.match_captures(case.pattern)
            self.match_aliases(case.pattern, subject_aliases)
            if case.guard:
                self.visit(case.guard)
                paths = [self.bindings] if self.irrefutable(case.pattern) else [remaining, self.bindings]
                remaining = merge_bindings(paths)
            elif self.irrefutable(case.pattern):
                remaining = None
            if self.statements(case.body):
                endings.append(self.bindings)
            if remaining is None:
                break
        if remaining is not None:
            endings.append(remaining)
        self.bindings = merge_bindings(endings)
        return bool(endings)

    def match_captures(self, pattern):
        for part in ast.walk(pattern):
            name = getattr(part, 'name', None)
            if name:
                self.bindings[name] = set()
            if isinstance(part, ast.MatchMapping) and part.rest:
                self.bindings[part.rest] = set()

    def match_aliases(self, pattern, aliases):
        if isinstance(pattern, ast.MatchAs):
            if pattern.name:
                self.bindings[pattern.name] = aliases.copy()
            if pattern.pattern:
                self.match_aliases(pattern.pattern, aliases)
        elif isinstance(pattern, ast.MatchOr):
            for part in pattern.patterns:
                self.match_aliases(part, aliases)

    def irrefutable(self, pattern):
        if isinstance(pattern, ast.MatchAs):
            return pattern.pattern is None or self.irrefutable(pattern.pattern)
        return isinstance(pattern, ast.MatchOr) and any(self.irrefutable(part) for part in pattern.patterns)

    def visit_Return(self, node):
        self.generic_visit(node)
        if self.exits:
            self.exits[-1].append((merge_bindings([self.bindings]), 'throw' if isinstance(node, ast.Raise) else type(node).__name__.lower()))
        return False

    visit_Raise = visit_Return
    visit_Break = visit_Return
    visit_Continue = visit_Return

    def visit_With(self, node):
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self.bind(item.optional_vars, set())
        return self.statements(node.body)

    visit_AsyncWith = visit_With

    def loop(self, body, condition=None):
        broken = []
        while True:
            initial = merge_bindings([self.bindings])
            normal, exits = self.captured_statements(body)
            continuing = [self.bindings] if normal else []
            for bindings, kind in exits:
                if kind == 'break':
                    broken.append(bindings)
                elif kind == 'continue':
                    continuing.append(bindings)
                elif self.exits:
                    self.exits[-1].append((bindings, kind))
            if continuing and condition:
                self.bindings = merge_bindings(continuing)
                self.visit(condition)
                continuing = [self.bindings]
            self.bindings = merge_bindings([initial, *continuing])
            if self.bindings == initial:
                return broken

    def loop_else(self, body, broken):
        normal = self.statements(body)
        endings = [self.bindings, *broken] if normal else broken
        self.bindings = merge_bindings(endings)
        return bool(endings)

    def visit_For(self, node):
        self.visit(node.iter)
        broken = self.loop([ast.Assign(targets=[node.target], value=ast.Constant(None)), *node.body])
        return self.loop_else(node.orelse, broken)

    visit_AsyncFor = visit_For

    def visit_While(self, node):
        self.visit(node.test)
        broken = self.loop(node.body, node.test)
        return self.loop_else(node.orelse, broken)

    def comprehension(self, node):
        self.visit(node.generators[0].iter)
        if isinstance(node, ast.GeneratorExp):
            return
        saved = merge_bindings([self.bindings])
        values = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        body = [ast.Expr(value=value) for value in values]
        for index in reversed(range(len(node.generators))):
            generator = node.generators[index]
            for condition in reversed(generator.ifs):
                body = [ast.If(test=condition, body=body, orelse=[])]
            iterable = generator.iter if index else ast.Constant(None)
            body = [ast.For(target=generator.target, iter=iterable, body=body, orelse=[])]
        self.statements(body)
        for generator in node.generators:
            for target in ast.walk(generator.target):
                if isinstance(target, ast.Name):
                    if target.id in saved:
                        self.bindings[target.id] = saved[target.id]
                    else:
                        self.bindings.pop(target.id, None)
