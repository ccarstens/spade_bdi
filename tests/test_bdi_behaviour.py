import unittest

from spade_bdi.bdi import prepare_datatypes_for_asl
from spade_bdi.bdi import BDIAgent
import agentspeak as asp


class TestBDIBehaviour(unittest.TestCase):

    def test_sanitizing(self):
        x = 5
        self.assertEqual(x, 5)

    def test_prepare_datatypes_for_asl_returns_tuple_where_all_strings_are_literals(self):
        arguments = ["agent", 12, asp.Literal("test", ("asdf"))]

        sanitized = prepare_datatypes_for_asl(arguments)

        self.assertIsInstance(sanitized, tuple)
        self.assertIsInstance(sanitized[0], asp.Literal)
        self.assertIsInstance(sanitized[1], int)
        self.assertIsInstance(sanitized[2], asp.Literal)






if __name__ == '__main__':
    unittest.main()


