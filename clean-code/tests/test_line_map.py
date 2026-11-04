import random
import unittest

from clean_code.git import Revisions
from tests.repo import ScratchRepository


def edited(lines: list[str], seed: int) -> list[str]:
    """Random deletions, insertions and rewrites of a line list."""
    chooser, result = random.Random(seed), []
    for line in lines:
        roll = chooser.random()
        if roll < 0.15:
            continue
        if roll < 0.3:
            result.append(f"new {chooser.random()}")
        result.append(f"changed {chooser.random()}" if roll > 0.9 else line)
    return result


class LineMapping(unittest.TestCase):
    def test_every_unchanged_head_line_maps_to_the_same_base_line(self):
        scratch = ScratchRepository()
        self.addCleanup(scratch.close)
        base_lines = [f"line {index}" for index in range(80)]
        base = scratch.commit({"a.txt": "\n".join(base_lines) + "\n"})
        for seed in range(25):
            with self.subTest(seed=seed):
                scratch.reset(base)
                head_lines = edited(base_lines, seed)
                head = scratch.commit({"a.txt": "\n".join(head_lines) + "\n"})
                line_map = scratch.repository.changes(Revisions(base, head))[0].line_map
                for number, text in enumerate(head_lines, 1):
                    base_number = line_map.base_line(number)
                    if base_number is not None:
                        self.assertEqual(base_lines[base_number - 1], text)


if __name__ == "__main__":
    unittest.main()
