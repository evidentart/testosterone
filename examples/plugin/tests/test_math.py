import unittest


class MathTest(unittest.TestCase):
    def test_add(self) -> None:
        self.assertEqual(1 + 1, 2)

    def test_sub(self) -> None:
        self.assertEqual(3 - 1, 2)
