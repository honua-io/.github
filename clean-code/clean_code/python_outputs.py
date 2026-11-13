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

    def exception_paths(self, node):
        initial = {name: values.copy() for name, values in self.bindings.items()}
        normal = self.statements(node.body) and self.statements(node.orelse)
        paths = [(self.bindings, normal)]
        exceptional = merge_bindings([initial, self.bindings])
        for handler in node.handlers:
            self.bindings = {name: values.copy() for name, values in exceptional.items()}
            if handler.name:
                self.bindings[handler.name] = set()
            normal = self.statements(handler.body)
            paths.append((self.bindings, normal))
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
