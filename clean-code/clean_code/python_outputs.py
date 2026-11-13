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
        if self.exits and isinstance(node, (ast.Call, ast.Attribute, ast.Subscript,
                                           ast.BinOp, ast.Compare, ast.Await, ast.Return, ast.Raise)):
            self.exits[-1].append((merge_bindings([self.bindings]), not isinstance(node, ast.Return)))
        return super().visit(node)

    def aliases(self, node):
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
        if isinstance(node.func, ast.Attribute) and node.func.attr in MUTATORS:
            self.outputs.update(self.aliases(node.func.value))
        self.generic_visit(node)

    def visit_Subscript(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.outputs.update(self.aliases(node.value))
        self.generic_visit(node)

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

    def visit_IfExp(self, node):
        self.visit(node.test)
        self.branches([[node.body], [node.orelse]])

    def captured_statements(self, body):
        self.exits.append([])
        normal = self.statements(body)
        exits = self.exits.pop()
        if self.exits:
            self.exits[-1].extend(exits)
        return normal, exits

    def exception_paths(self, node):
        normal, exits = self.captured_statements(node.body)
        exceptional = merge_bindings([bindings for bindings, throws in exits if throws])
        if normal:
            normal, other_exits = self.captured_statements(node.orelse)
            exits.extend(other_exits)
        paths = [(self.bindings, normal), (merge_bindings([bindings for bindings, _ in exits]), False)]
        for handler in node.handlers:
            self.bindings = merge_bindings([exceptional])
            if handler.name:
                self.bindings[handler.name] = set()
            normal, handler_exits = self.captured_statements(handler.body)
            paths.extend([(self.bindings, normal), (merge_bindings([bindings for bindings, _ in handler_exits]), False)])
        return paths

    def visit_Try(self, node):
        endings = []
        for bindings, normal in self.exception_paths(node):
            self.bindings = {name: values.copy() for name, values in bindings.items()}
            final_normal = self.statements(node.finalbody)
            if normal and final_normal:
                endings.append(self.bindings)
        self.bindings = merge_bindings(endings)
        return bool(endings)

    visit_TryStar = visit_Try

    def visit_If(self, node):
        self.visit(node.test)
        return self.branches([node.body, node.orelse])

    def visit_Return(self, node):
        self.generic_visit(node)
        return False

    visit_Raise = visit_Return

    def visit_With(self, node):
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self.bind(item.optional_vars, set())
        return self.statements(node.body)

    visit_AsyncWith = visit_With

    def visit_For(self, node):
        self.visit(node.iter)
        self.branches([[], [ast.Assign(targets=[node.target], value=ast.Constant(None)), *node.body]])
        self.statements(node.orelse)

    visit_AsyncFor = visit_For

    def visit_While(self, node):
        self.visit(node.test)
        self.branches([[], node.body])
        self.statements(node.orelse)

    def comprehension(self, node):
        saved = self.bindings.copy()
        for generator in node.generators:
            self.visit(generator.iter)
            self.bind(generator.target, set())
            self.statements(generator.ifs)
        if isinstance(node, ast.DictComp):
            self.visit(node.key)
            self.visit(node.value)
        else:
            self.visit(node.elt)
        self.bindings = saved
