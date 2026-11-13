import unittest

from clean_code.lexing import lex_files


class OutputAssertions(unittest.TestCase):
    def outputs(self, path, source):
        functions = lex_files({path: source})[path].functions
        return {parameter.name for function in functions for parameter in function.parameters if parameter.is_output}

