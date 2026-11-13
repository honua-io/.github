from tests.output_support import OutputAssertions


class OutputExits(OutputAssertions):
    def test_loop_control_runs_finally_and_skips_unreachable_mutation(self):
        for control in ('break', 'continue'):
            cases = [
                ('a.py', f'def collect(items):\n    alias = []\n    for i in range(2):\n        try:\n            {control}\n        finally:\n            alias = []\n        items.clear()\n    alias.clear()\n'),
                ('a.ts', f'function collect(items) {{ let alias = []; for(let i=0;i<2;i++) {{ try {{ {control}; }} finally {{ alias = []; }} items.push(1); }} alias.push(1); }}'),
            ]
            for path, source in cases:
                with self.subTest(path=path, control=control):
                    self.assertEqual(self.outputs(path, source), set())

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

