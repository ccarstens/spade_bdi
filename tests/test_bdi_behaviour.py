import unittest

from spade_bdi.bdi import BDIAgent


class TestBDIBehaviour(unittest.TestCase):

    def test_sanitizing(self):
        x = 5
        self.assertEqual(x, 5)

    def test_behav(self):
        b = BDIAgent.BDIBehaviour()




if __name__ == '__main__':
    unittest.main()


