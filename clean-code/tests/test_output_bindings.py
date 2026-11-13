import unittest

from clean_code.lexing import lex_files


class OutputBindings(unittest.TestCase):
    def outputs(self, path, source):
        functions = lex_files({path: source})[path].functions
        return {parameter.name for function in functions for parameter in function.parameters if parameter.is_output}

    def test_local_copies_and_shadowing_are_not_outputs(self):
        cases = [
            ('a.py', 'def collect(items):\n    items = list(items)\n    items.append(1)\n'),
            ('a.py', 'def collect(items):\n    return [items.append(1) for items in [[], []]]\n'),
            ('a.ts', 'function collect(items: number[]) { items = [...items]; items.push(1); }'),
            ('a.ts', 'function collect(items: number[]) { { const items: number[] = []; items.push(1); } }'),
            ('a.cjs', 'class C { constructor(checker) { this.checker = checker; } }'),
            ('a.cjs', 'function collect({items}) { const local = []; local.push(1); }'),
        ]
        for path, source in cases:
            with self.subTest(source=source):
                self.assertEqual(self.outputs(path, source), set())

    def test_mutations_of_original_inputs_and_aliases_are_outputs(self):
        cases = [
            ('a.py', 'def collect(items):\n    items.sort()\n    items.clear()\n'),
            ('a.py', 'def collect(items):\n    copy = items\n    copy.pop()\n'),
            ('a.ts', 'function collect(items: number[]) { items[0]++; --items[1]; }'),
            ('a.ts', 'function collect(items: number[]) { const alias = items; alias.push(1); }'),
            ('a.py', 'def collect(items, flag):\n    if flag:\n        items = []\n    items.clear()\n'),
            ('a.ts', 'function collect(items: number[], flag: boolean) { if(flag) items = []; items.push(1); }'),
        ]
        for path, source in cases:
            with self.subTest(source=source):
                self.assertEqual(self.outputs(path, source), {'items'})

    def test_terminated_paths_and_with_targets_are_not_output_aliases(self):
        cases = [
            ('a.py', 'def collect(items, flag):\n    if flag:\n        items = []\n    else:\n        return\n    items.clear()\n'),
            ('a.py', 'def collect(items, flag):\n    if flag:\n        items = []\n    else:\n        raise ValueError()\n    items.clear()\n'),
            ('a.py', 'def collect(items):\n    with factory() as items:\n        items.clear()\n'),
            ('a.ts', 'function collect(items: number[], flag: boolean) { if(flag) items = []; else return; items.push(1); }'),
            ('a.ts', 'function collect(items: number[], flag: boolean) { if(flag) items = []; else throw Error(); items.push(1); }'),
        ]
        for path, source in cases:
            with self.subTest(source=source):
                self.assertEqual(self.outputs(path, source), set())

    def test_zero_iteration_loop_preserves_input_alias(self):
        for loop in ['while(n-- > 0)', 'for(;n-- > 0;)', 'for(const value of values)']:
            source = f'function collect(items: number[], n: number) {{ {loop} {{ items = []; }} items.push(1); }}'
            with self.subTest(loop=loop):
                self.assertEqual(self.outputs('a.ts', source), {'items'})

    def test_exception_paths_preserve_possible_input_mutations(self):
        cases = [
            ('a.py', 'def collect(items):\n    try:\n        may_fail()\n    except ValueError:\n        items = []\n    items.clear()\n'),
            ('a.ts', 'function collect(items: number[]) { try { mayFail(); } catch { items = []; } items.push(1); }'),
            ('a.ts', 'function collect(items: number[]) { try { mayFail(); } catch { items.push(1); } }'),
            ('a.ts', 'function collect(items: number[]) { try { return; } finally { items.push(1); } }'),
            ('a.py', 'def collect(items):\n    try:\n        return\n    finally:\n        items.clear()\n'),
        ]
        for path, source in cases:
            with self.subTest(source=source):
                self.assertEqual(self.outputs(path, source), {'items'})

    def test_finally_rebinding_applies_to_all_continuing_paths(self):
        cases = [
            ('a.py', 'def collect(items):\n    try:\n        may_fail()\n    finally:\n        items = []\n    items.clear()\n'),
            ('a.ts', 'function collect(items: number[]) { try { mayFail(); } finally { items = []; } items.push(1); }'),
        ]
        for path, source in cases:
            with self.subTest(source=source):
                self.assertEqual(self.outputs(path, source), set())

    def test_comprehension_does_not_hide_outer_input_after_its_scope(self):
        source = 'def collect(items):\n    values = [items for items in []]\n    items.clear()\n'
        self.assertEqual(self.outputs('a.py', source), {'items'})


class ConstructorForms(unittest.TestCase):
    def test_implicit_and_primary_constructors_retain_parameter_metadata(self):
        for source in [
            'class C<T> where T : class { C(int a,int b,int c,int d,bool enabled) {} }',
            'class C { C(int a,int b,int c,int d,bool enabled) {} }',
            'class C(int a,int b,int c,int d,bool enabled) {}',
            'record C(int a,int b,int c,int d,bool enabled);',
            'record struct C(int a,int b,int c,int d,bool enabled);',
        ]:
            with self.subTest(source=source):
                functions = lex_files({'C.cs': source})['C.cs'].functions
                self.assertEqual(len(functions), 1)
                self.assertTrue(functions[0].is_constructor)
                self.assertEqual(len(functions[0].parameters), 5)
                self.assertTrue(functions[0].parameters[-1].is_boolean)

    def test_object_initializer_is_not_a_constructor_declaration(self):
        source = 'class C { static C Create() { return new C(1,2,3,4) { Value = 1 }; } }'
        functions = lex_files({'C.cs': source})['C.cs'].functions
        self.assertFalse(any(function.is_constructor for function in functions))
