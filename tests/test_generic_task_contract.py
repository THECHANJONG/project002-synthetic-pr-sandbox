"""Regression tests for generic, non-executing task contract."""
import json
import unittest
from scripts.generic_task_contract import InvalidTask, parse_task

BASE = {
    "schema_version": 1,
    "task_id": "demo-1",
    "repository": "example/safe-project",
    "base_sha": "a" * 40,
    "objective": "Fix a small deterministic parser regression.",
    "allowed_paths": ["src/parser.py", "tests/test_parser.py"],
    "acceptance_tests": ["Parser regression passes", "No original data changes"],
}

class ContractTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_task(json.dumps(BASE))["task_id"], "demo-1")

    def test_duplicate_json_key(self):
        with self.assertRaises(InvalidTask):
            parse_task(json.dumps(BASE)[:-1] + ', "task_id":"other"}')

    def test_nonfinite(self):
        with self.assertRaises(InvalidTask):
            parse_task(json.dumps(BASE).replace('"schema_version": 1', '"schema_version": NaN'))

    def test_boolean_schema(self):
        self.reject(schema_version=True)

    def test_unpinned_head(self):
        self.reject(base_sha="main")

    def test_traversal(self):
        for path in ("../secrets", "src/../../secret", "/root/file", "src\\bad", "src//bad"):
            with self.subTest(path=path):
                self.reject(allowed_paths=[path])

    def test_unknown_field(self):
        self.reject(shell_command="curl example.com")

    def test_empty_tests(self):
        self.reject(acceptance_tests=[])

    def test_duplicate_paths(self):
        self.reject(allowed_paths=["src/a.py", "src/a.py"])

    def test_oversize(self):
        with self.assertRaises(InvalidTask):
            parse_task(" " * 32769)

    def reject(self, **changes):
        value = dict(BASE)
        value.update(changes)
        with self.assertRaises(InvalidTask):
            parse_task(json.dumps(value))

if __name__ == "__main__":
    unittest.main()
