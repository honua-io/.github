import unittest

from tests.test_rules import PullRequest, rule_keys


class OutputArguments(unittest.TestCase):
    def findings(self, base, head):
        pull_request = PullRequest(base)
        self.addCleanup(pull_request.close)
        return rule_keys(pull_request.findings(head))

    def test_mutating_an_existing_input_is_new_output(self):
        cases = {
            'src/a.py': ('def collect(result):\n    return len(result)\n',
                         'def collect(result):\n    result.append(1)\n    return len(result)\n'),
            'src/a.ts': ('export function collect(result: number[]) {\n  return result.length;\n}\n',
                         'export function collect(result: number[]) {\n  result.push(1);\n  return result.length;\n}\n'),
            'src/A.cs': ('class C {\n    int Read(int value) { return value; }\n}\n',
                         'class C {\n    int Read(ref int value) { return value; }\n}\n'),
        }
        for path, (base, head) in cases.items():
            with self.subTest(path=path):
                self.assertIn('clean-code/output-argument', self.findings({path: base}, {path: head}))

    def test_existing_output_can_be_touched_without_repeating_the_finding(self):
        cases = {
            'src/a.py': 'def collect(result):\n    result.append(1)\n',
            'src/a.ts': 'export function collect(result: number[]) {\n  result.push(1);\n}\n',
            'src/A.cs': 'class C {\n    void Read(out int value) { value = 1; }\n}\n',
        }
        for path, base in cases.items():
            with self.subTest(path=path):
                self.assertNotIn('clean-code/output-argument', self.findings({path: base}, {path: base.replace('1', '2')}))

    def test_nested_scope_parameter_does_not_mark_outer_input(self):
        cases = {
            'src/a.py': 'def collect(result):\n    def nested(result):\n        result.append(1)\n    return result\n',
            'src/a.ts': 'export function collect(result: number[]) {\n  function nested(result: number[]) { result.push(1); }\n  return result;\n}\n',
        }
        for path, source in cases.items():
            with self.subTest(path=path):
                pull_request = PullRequest({'README.md': 'fixture\n'})
                self.addCleanup(pull_request.close)
                found = [f for f in pull_request.findings({path: source}) if f.rule.key == 'clean-code/output-argument']
                self.assertEqual(len(found), 1)
                self.assertIn('nested', found[0].message)

    def test_direct_index_assignment_is_output(self):
        for path, source in {
            'src/a.py': 'def collect(result):\n    result[0] = 1\n',
            'src/a.ts': 'export function collect(result: number[]) { result[0] = 1; }\n',
        }.items():
            with self.subTest(path=path):
                self.assertIn('clean-code/output-argument', self.findings({'README.md': 'x\n'}, {path: source}))


class DecisionHistory(unittest.TestCase):
    def test_dated_decisions_and_rollout_identifiers_are_rejected(self):
        pull_request = PullRequest({'README.md': 'fixture\n'})
        self.addCleanup(pull_request.close)
        for text in ('Decision: keep this path.', 'Founder requested this.', 'R19 selects this path.',
                     'rc.3 uses this path.', 'Validated 2026-11-13.', 'Validated 2026/11/13.'):
            with self.subTest(text=text):
                found = pull_request.findings({'src/a.py': '# ' + text + '\nvalue = 1\n'})
                self.assertIn('clean-code/history-comment', rule_keys(found))
