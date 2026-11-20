import unittest
from generated.multiply_numbers import multiply_numbers

class GeneratedMultiplierTests(unittest.TestCase):
    def test_cases(self):
        for left, right, expected in [(3, 4, 12), (-3, 4, -12), (0, 9, 0), (-2, -5, 10), (2.5, 4, 10)]:
            with self.subTest(left=left, right=right):
                self.assertEqual(multiply_numbers(left, right), expected)
