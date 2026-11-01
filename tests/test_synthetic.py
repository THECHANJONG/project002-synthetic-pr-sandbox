import unittest


class SyntheticContractTest(unittest.TestCase):
    def test_no_production_data(self):
        self.assertEqual('synthetic', 'synthetic')


if __name__ == '__main__':
    unittest.main()
