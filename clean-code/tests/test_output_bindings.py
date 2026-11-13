import unittest

from clean_code.lexing import lex_files


class OutputBindings(unittest.TestCase):
    def outputs(self, path, source):
        functions = lex_files({path: source})[path].functions
        return {parameter.name for function in functions for parameter in function.parameters if parameter.is_output}

    def test_chained_comparison_rebinding_can_be_skipped(self):
        cases = [
            ('flag == 0 == (items := [])', {'items'}),
            ('(items := []) == 0 == flag', set()),
            ('flag == (items := [])', set()),
        ]
        for condition, expected in cases:
            source = f'def collect(items, flag):\n    match items:\n        case _ if {condition}: pass\n    items.clear()\n'
            with self.subTest(condition=condition):
                self.assertEqual(self.outputs('a.py', source), expected)

    def test_typescript_do_loop_aliases_reach_later_iterations(self):
        cases = [
            ('let alias = []; do { alias.push(1); alias = items; } while(n-- > 0);', {'items'}),
            ('do { items = []; } while(n-- > 0); items.push(1);', set()),
            ('do { items = []; break; } while(n-- > 0); items.push(1);', set()),
            ('let alias = []; do { alias = items; continue; } while(n-- > 0); alias.push(1);', {'items'}),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                self.assertEqual(self.outputs('a.ts', f'function collect(items, n) {{ {body} }}'), expected)

    def test_typescript_assertions_preserve_aliases(self):
        for expression in ('items as number[]', '<number[]>items', 'items!', 'items satisfies number[]'):
            source = f'function collect(items: number[]) {{ const alias = {expression}; alias.push(1); }}'
            with self.subTest(expression=expression):
                self.assertEqual(self.outputs('a.ts', source), {'items'})
        source = 'function collect(items: number[]) { const alias = [...items] as number[]; alias.push(1); }'
        self.assertEqual(self.outputs('a.ts', source), set())

    def test_comprehension_walrus_updates_enclosing_aliases(self):
        cases = [
            ('alias = []', '[(alias := items) for index in range(1)]', 'alias.clear()', {'items'}),
            ('alias = items', '[(alias := []) for index in range(0)]', 'alias.clear()', {'items'}),
            ('alias = []', '[(alias := items) for index in range(1) if flag]', 'alias.clear()', {'items'}),
            ('alias = []', '{index: (alias := items) for index in range(1)}', 'alias.clear()', {'items'}),
            ('alias = []', '[alias.clear() or (alias := items) for index in range(2)]', 'pass', {'items'}),
            ('alias = []', '[items.clear() for items in [[]]]', 'alias.clear()', set()),
        ]
        for setup, expression, ending, expected in cases:
            source = f'def collect(items, flag):\n    {setup}\n    values = {expression}\n    {ending}\n'
            with self.subTest(expression=expression):
                self.assertEqual(self.outputs('a.py', source), expected)

    def test_irrefutable_match_guard_rebinding_applies_to_continuing_paths(self):
        cases = [
            ('_ if (items := [])', set()),
            ('alias if (items := [0])', set()),
            ('[] | _ if (items := [])', set()),
            ('_ if flag and (items := [])', {'items'}),
            ('[] if (items := [])', {'items'}),
        ]
        for pattern, expected in cases:
            source = f'def collect(items, flag):\n    match items:\n        case {pattern}: pass\n    items.clear()\n'
            with self.subTest(pattern=pattern):
                self.assertEqual(self.outputs('a.py', source), expected)

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

    def test_short_circuit_paths_preserve_input_aliases(self):
        for operator in ('and', 'or'):
            source = f'def collect(items, flag):\n    flag {operator} (items := [])\n    items.clear()\n'
            with self.subTest(operator=operator):
                self.assertEqual(self.outputs('a.py', source), {'items'})
        for operator in ('&&', '||', '??'):
            source = f'function collect(items, flag) {{ flag {operator} (items = []); items.push(1); }}'
            with self.subTest(operator=operator):
                self.assertEqual(self.outputs('a.ts', source), {'items'})

    def test_mutator_receiver_is_resolved_before_arguments(self):
        cases = [
            ('a.py', 'def collect(items):\n    items.append(items := [])\n', {'items'}),
            ('a.py', 'def collect(items):\n    (items := []).clear()\n', set()),
            ('a.ts', 'function collect(items) { items.push(items = []); }', {'items'}),
            ('a.ts', 'function collect(items) { (items = []).push(1); }', set()),
        ]
        for path, source, expected in cases:
            with self.subTest(path=path, source=source):
                self.assertEqual(self.outputs(path, source), expected)

    def test_python_index_base_is_evaluated_before_receiver_capture(self):
        cases = [
            ('(items := [0])[0] = 1', set()),
            ('(alias := items)[0] = 1', {'items'}),
            ('items[(items := [0], 0)[1]] = 1', {'items'}),
            ('del (items := [0])[0]', set()),
            ('del (alias := items)[0]', {'items'}),
        ]
        for statement, expected in cases:
            source = f'def collect(items):\n    alias = [0]\n    {statement}\n'
            with self.subTest(statement=statement):
                self.assertEqual(self.outputs('a.py', source), expected)

    def test_match_subject_alias_survives_capture_and_guard_rebinding(self):
        cases = [
            ('case items: items.clear()', {'items'}),
            ('case items if (items := []): pass\n        case alias: alias.clear()', {'items'}),
        ]
        for pattern, expected in cases:
            source = f'def collect(items):\n    match items:\n        {pattern}\n'
            with self.subTest(pattern=pattern):
                self.assertEqual(self.outputs('a.py', source), expected)

    def test_indexed_assignment_preserves_evaluated_receiver(self):
        for operator in ('=', '+=', '&&=', '||=', '??='):
            source = f'function collect(items) {{ items[0] {operator} (items = []); }}'
            with self.subTest(operator=operator):
                self.assertEqual(self.outputs('a.ts', source), {'items'})

    def test_index_side_effects_follow_receiver_capture(self):
        for operator in ('=', '+=', '&&=', '||=', '??='):
            source = f'function collect(items) {{ items[(items = [], 0)] {operator} 1; }}'
            with self.subTest(operator=operator):
                self.assertEqual(self.outputs('a.ts', source), {'items'})
        source = 'function collect(items) { (items = [])[(items = [], 0)] = 1; }'
        self.assertEqual(self.outputs('a.ts', source), set())

    def test_switch_and_match_merge_alternative_paths(self):
        cases = [
            ('a.ts', 'function collect(items, flag) { let alias = items; switch(flag) { case 0: break; default: alias = []; } alias.push(1); }', {'items'}),
            ('a.ts', 'function collect(items, flag) { let alias = items; switch(flag) { case 0: alias = []; default: alias = []; } alias.push(1); }', set()),
            ('a.ts', 'function collect(items, flag) { switch(flag) { case 0: items = []; break; default: return; } items.push(1); }', set()),
            ('a.ts', 'function collect(items, flag) { switch(flag) { case 0: items = []; break; } items.push(1); }', {'items'}),
            ('a.py', 'def collect(items, flag):\n    alias = items\n    match flag:\n        case 0: pass\n        case _: alias = []\n    alias.clear()\n', {'items'}),
            ('a.py', 'def collect(items, flag):\n    match flag:\n        case 0: items = []\n        case _: return\n    items.clear()\n', set()),
            ('a.py', 'def collect(items, flag):\n    match flag:\n        case items: items.clear()\n', {'flag'}),
            ('a.py', 'def collect(items):\n    match items:\n        case alias: alias.clear()\n', {'items'}),
            ('a.py', 'def collect(items, flag):\n    match flag:\n        case 0: items = []\n    items.clear()\n', {'items'}),
        ]
        for path, source, expected in cases:
            with self.subTest(path=path, source=source):
                self.assertEqual(self.outputs(path, source), expected)

    def test_match_capture_mutates_subject_instead_of_shadowed_input(self):
        source = 'def collect(items, flag):\n    match flag:\n        case items: items.clear()\n'
        namespace = {}
        exec(source, namespace)
        original, subject = [1], [2]
        namespace['collect'](original, subject)
        self.assertEqual(original, [1])
        self.assertEqual(subject, [])
        self.assertEqual(self.outputs('a.py', source), {'flag'})

    def test_loop_break_and_continue_preserve_exit_bindings(self):
        for control in ('break', 'continue'):
            cases = [
                ('a.py', f'def collect(items, flag):\n    alias = []\n    for i in range(2):\n        if flag:\n            alias = items\n            {control}\n        alias = []\n    alias.clear()\n'),
                ('a.ts', f'function collect(items, flag) {{ let alias = []; for(let i=0;i<2;i++) {{ if(flag) {{ alias = items; {control}; }} alias = []; }} alias.push(1); }}'),
            ]
            for path, source in cases:
                with self.subTest(path=path, control=control):
                    self.assertEqual(self.outputs(path, source), {'items'})

    def test_loop_control_runs_finally_and_skips_unreachable_mutation(self):
        for control in ('break', 'continue'):
            cases = [
                ('a.py', f'def collect(items):\n    alias = []\n    for i in range(2):\n        try:\n            {control}\n        finally:\n            alias = []\n        items.clear()\n    alias.clear()\n'),
                ('a.ts', f'function collect(items) {{ let alias = []; for(let i=0;i<2;i++) {{ try {{ {control}; }} finally {{ alias = []; }} items.push(1); }} alias.push(1); }}'),
            ]
            for path, source in cases:
                with self.subTest(path=path, control=control):
                    self.assertEqual(self.outputs(path, source), set())

    def test_loop_else_does_not_overwrite_break_bindings(self):
        source = 'def collect(items):\n    alias = []\n    for i in range(2):\n        alias = items\n        break\n    else:\n        alias = []\n    alias.clear()\n'
        self.assertEqual(self.outputs('a.py', source), {'items'})

    def test_logical_assignments_preserve_skipped_binding(self):
        for operator in ('&&=', '||=', '??='):
            source = f'function collect(items, flag) {{ flag {operator} (items = []); items.push(1); }}'
            with self.subTest(operator=operator):
                self.assertEqual(self.outputs('a.ts', source), {'items'})

    def test_later_loop_iterations_retain_aliases(self):
        cases = [
            ('a.py', 'def collect(items):\n    alias = []\n    for index in range(2):\n        alias.clear()\n        alias = items\n'),
            ('a.ts', 'function collect(items) { let alias = []; for(let i=0;i<2;i++) { alias.push(1); alias = items; } }'),
        ]
        for path, source in cases:
            with self.subTest(path=path):
                self.assertEqual(self.outputs(path, source), {'items'})

    def test_exception_snapshot_follows_argument_evaluation(self):
        cases = [
            ('a.py', 'def collect(items):\n    alias = []\n    try:\n        consume(alias := items)\n    except Exception:\n        alias.clear()\n'),
            ('a.ts', 'function collect(items) { let alias = []; try { consume(alias = items); } catch { alias.push(1); } }'),
        ]
        for path, source in cases:
            with self.subTest(path=path):
                self.assertEqual(self.outputs(path, source), {'items'})

    def test_exception_snapshot_follows_receiver_evaluation(self):
        source = 'def collect(items):\n    try:\n        return (items := []).copy()\n    finally:\n        items.clear()\n'
        self.assertEqual(self.outputs('a.py', source), set())

    def test_conditional_expression_preserves_skipped_binding(self):
        source = 'def collect(items, flag):\n    (items := []) if flag else None\n    items.clear()\n'
        self.assertEqual(self.outputs('a.py', source), {'items'})

    def test_finally_sees_exceptions_before_and_between_rebindings(self):
        cases = [
            ('a.py', 'def collect(items):\n    try:\n        may_fail()\n        items = []\n    finally:\n        items.clear()\n'),
            ('a.ts', 'function collect(items) { try { mayFail(); items = []; } finally { items.push(1); } }'),
            ('a.py', 'def collect(items):\n    alias = []\n    try:\n        alias = items\n        may_fail()\n        alias = []\n        items = []\n    finally:\n        alias.clear()\n'),
            ('a.ts', 'function collect(items) { let alias = []; try { alias = items; mayFail(); alias = []; items = []; } finally { alias.push(1); } }'),
        ]
        for path, source in cases:
            with self.subTest(source=source):
                self.assertEqual(self.outputs(path, source), {'items'})

    def test_return_does_not_enter_exception_handler(self):
        cases = [
            ('a.py', 'def collect(items, other):\n    try:\n        return\n    except Exception:\n        items = other\n    finally:\n        items.clear()\n'),
            ('a.ts', 'function collect(items, other) { try { return; } catch { items = other; } finally { items.push(1); } }'),
        ]
        for path, source in cases:
            with self.subTest(path=path):
                self.assertEqual(self.outputs(path, source), {'items'})

    def test_nested_finally_transforms_exception_bindings(self):
        for binding, expected in [('alias = items', {'items'}), ('alias = []', set())]:
            cases = [
                ('a.py', f'def collect(items):\n    alias = items\n    try:\n        try:\n            may_fail()\n        finally:\n            {binding}\n    except Exception:\n        alias.clear()\n'),
                ('a.ts', f'function collect(items) {{ let alias = items; try {{ try {{ mayFail(); }} finally {{ {binding}; }} }} catch {{ alias.push(1); }} }}'),
            ]
            for path, source in cases:
                with self.subTest(path=path, binding=binding):
                    self.assertEqual(self.outputs(path, source), expected)

    def test_return_expression_rebinding_precedes_finally(self):
        cases = [
            ('a.py', 'def collect(items):\n    try:\n        return (items := [])\n    finally:\n        items.clear()\n'),
            ('a.ts', 'function collect(items) { try { return (items = []); } finally { items.push(1); } }'),
        ]
        for path, source in cases:
            with self.subTest(path=path):
                self.assertEqual(self.outputs(path, source), set())

    def test_safe_rebinding_before_finally_does_not_mutate_input(self):
        for path, source in [
            ('a.py', 'def collect(items):\n    try:\n        items = []\n    finally:\n        items.clear()\n'),
            ('a.ts', 'function collect(items) { try { items = []; } finally { items.push(1); } }'),
        ]:
            with self.subTest(path=path):
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
