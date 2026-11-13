from tests.output_support import OutputAssertions


class OutputTargets(OutputAssertions):
    def test_literal_indexed_mutators(self):
        for expression, expected in [
            ('items["push"](1)', {'items'}),
            ("items['clear']()", {'items'}),
            ('items[`push`](1)', {'items'}),
            ('items["slice"]()', set()),
            ('items = []; items["push"](1)', set()),
        ]:
            with self.subTest(expression=expression):
                self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {expression}; }}'), expected)

    def test_destructured_member_writes(self):
        for statement in [
            '[items[0]] = [1]', '({value: items[0]} = {value: 1})',
            '[[items[0]]] = [[1]]', 'for ([items[0]] of [[1]]) {}',
            'for ({value: items[0]} of [{value: 1}]) {}',
        ]:
            with self.subTest(statement=statement):
                self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {statement}; }}'), {'items'})

    def test_destructuring_clears_rebound_aliases(self):
        for statement in ['[items] = [[]]', '({value: items} = {value: []})', '[[items]] = [[[]]]']:
            with self.subTest(statement=statement):
                source = f'function collect(items) {{ {statement}; items.push(1); }}'
                self.assertEqual(self.outputs('a.ts', source), set())

    def test_destructuring_preserves_direct_literal_aliases(self):
        for statement in [
            'let [alias] = [items]', 'let {value: alias} = {value: items}',
            'let alias; [alias] = [items]', 'let alias; ({value: alias} = {value: items})',
        ]:
            with self.subTest(statement=statement):
                source = f'function collect(items) {{ {statement}; alias.push(1); }}'
                self.assertEqual(self.outputs('a.ts', source), {'items'})

    def test_destructuring_snapshots_sources_before_rebinding(self):
        source = 'function collect(items) { let alias; [items, alias] = [[], items]; alias.push(1); }'
        self.assertEqual(self.outputs('a.ts', source), {'items'})
