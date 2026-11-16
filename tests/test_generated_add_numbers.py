"""Minimal executable check for the exact generated Qwen artifact.

Origin: Actions run 42096325448, attempt 2, artifact 14222556619.
The generated source is published verbatim; this test is human/assistant-authored.
"""
import unittest

from generated.add_numbers import add_numbers


class GeneratedAdderTests(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(add_numbers(2, 3), 5)

    def test_zero(self):
        self.assertEqual(add_numbers(0, 0), 0)

    def test_negative(self):
        self.assertEqual(add_numbers(-9, 2), -7)


if __name__ == "__main__":
    unittest.main()
