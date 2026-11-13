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

    def test_comprehension_does_not_hide_outer_input_after_its_scope(self):
        source = 'def collect(items):\n    values = [items for items in []]\n    items.clear()\n'
        self.assertEqual(self.outputs('a.py', source), {'items'})


class ConstructorForms(unittest.TestCase):
    def test_implicit_and_primary_constructors_retain_parameter_metadata(self):
        for source in [
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
