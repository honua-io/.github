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
            'let {items: alias} = {items}',
        ]:
            with self.subTest(statement=statement):
                source = f'function collect(items) {{ {statement}; alias.push(1); }}'
                self.assertEqual(self.outputs('a.ts', source), {'items'})

    def test_destructuring_snapshots_sources_before_rebinding(self):
        source = 'function collect(items) { let alias; [items, alias] = [[], items]; alias.push(1); }'
        self.assertEqual(self.outputs('a.ts', source), {'items'})

    def test_destructuring_evaluates_rhs_before_targets(self):
        for statement, expected in [
            ('let alias = []; [alias[0]] = (alias = items, [1])', {'items'}),
            ('[items[0]] = (items = [], [1])', set()),
            ('[items, items[0]] = [[], 1]', set()),
            ('let alias; [alias, alias[0]] = [items, 1]', {'items'}),
            ('let alias; [alias, items] = [items, []]; alias.push(1)', {'items'}),
            ('let alias; [alias, items] = [items, items = []]; alias.push(1)', {'items'}),
            ('let alias; ({value: alias, reset: items} = {value: items, reset: items = []}); alias.push(1)', {'items'}),
        ]:
            with self.subTest(statement=statement):
                self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {statement}; }}'), expected)

    def test_rest_bindings_create_fresh_collections(self):
        for statement in [
            'const [...copy] = [items]; copy.push(1)',
            'let copy; [...copy] = [items]; copy.push(1)',
            'const {value, ...copy} = {value: items}; copy.extra = 1',
        ]:
            with self.subTest(statement=statement):
                self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {statement}; }}'), set())

    def test_destructuring_defaults_follow_selected_paths(self):
        for statement, expected in [
            ('const [value = items.pop()] = []', {'items'}),
            ('const [value = items.pop()] = [1]', set()),
            ('const [value = items.pop()] = [undefined]', {'items'}),
            ('const [alias = items] = []; alias.push(1)', {'items'}),
            ('const [alias = items] = [[]]; alias.push(1)', set()),
            ('const {value = items.pop()} = {}', {'items'}),
            ('let alias; ({alias = items} = {}); alias.push(1)', {'items'}),
            ('const [value = items.pop()] = other', {'items'}),
            ('const [[alias] = [items]] = []; alias.push(1)', {'items'}),
            ('[items[0] = (items = [], 1)] = []', {'items'}),
        ]:
            with self.subTest(statement=statement):
                self.assertEqual(self.outputs('a.ts', f'function collect(items, other) {{ {statement}; }}'), expected)

    def test_equivalent_object_keys_preserve_aliases(self):
        for target, source in [('value', '"value"'), ('"value"', 'value'),
                               ('["value"]', 'value'), ('value', '["value"]'),
                               ('1', '1e0'), ('[1]', '"1"')]:
            with self.subTest(target=target, source=source):
                body = f'const {{{target}: alias}} = {{{source}: items}}; alias.push(1);'
                self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {body} }}'), {'items'})

    def test_wrapped_and_spread_source_snapshots(self):
        for source in ['(copy = [items, items = []])', '[items, items = [], ...[]]',
                       '[...[items, items = []]]', '[...[], items, items = []]']:
            with self.subTest(source=source):
                body = f'let copy; const [alias] = {source}; alias.push(1);'
                self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {body} }}'), {'items'})
        body = 'let copy; const {value: alias} = (copy = {...{value: items}, reset: items = []}); alias.push(1);'
        self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {body} }}'), {'items'})

    def test_known_values_skip_defaults(self):
        for value in ['true', 'false', 'null', '0', '""', '[]', '{}']:
            with self.subTest(value=value):
                body = f'const [value = items.pop()] = [{value}];'
                self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {body} }}'), set())

    def test_shadowed_undefined_preserves_aliases(self):
        body = 'const undefined = items; const [alias = []] = [undefined]; alias.push(1);'
        self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {body} }}'), {'items'})
        body = 'const [alias = []] = [undefined]; alias.push(1);'
        self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {body} }}'), set())

    def test_spread_sources_preserve_default_selection(self):
        for body, expected in [
            ('const [value = items.pop()] = [...[], undefined]', {'items'}),
            ('const [value = items.pop()] = [...[false]]', set()),
            ('const [...[value = items.pop()]] = [...[]]', {'items'}),
            ('const {value = items.pop()} = {...{value: false}}', set()),
            ('const [value = items.pop()] = [...other]', {'items'}),
        ]:
            with self.subTest(body=body):
                self.assertEqual(self.outputs('a.ts', f'function collect(items, other) {{ {body} }}'), expected)

    def test_rest_parameters_are_fresh_collections(self):
        for body, expected in [
            ('function collect(...items) { items.sort(); return items; }', set()),
            ('function collect(items, ...rest) { rest.push(1); items.sort(); }', {'items'}),
            ('function collect(items, ...rest) { const alias = rest; alias.clear(); }', set()),
            ('function collect(items, ...rest) { rest = items; rest.push(1); }', {'items'}),
        ]:
            with self.subTest(body=body):
                self.assertEqual(self.outputs('a.ts', body), expected)

    def test_signed_literal_keys_preserve_aliases(self):
        for target, source, expected in [
            ('[-1]', '[-1]', {'items'}), ('[-1]', '"-1"', {'items'}),
            ('"-1"', '[-1]', {'items'}), ('[+1]', '1', {'items'}),
            ('[-0]', '"0"', {'items'}), ('[-1]', '[1]', set()),
        ]:
            with self.subTest(target=target, source=source):
                body = f'const {{{target}: alias}} = {{{source}: items}}; alias.push(1);'
                self.assertEqual(self.outputs('a.ts', f'function collect(items) {{ {body} }}'), expected)
