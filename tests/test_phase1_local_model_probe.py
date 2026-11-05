"""Offline proof-contract tests; not a substitute for a real-model Actions run."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.phase1_local_model_probe import (
    BRANCH, MODEL_REVISION, ProbeBlocked, REPOSITORY,
    normalize_candidate, run_probe, validate_environment,
)

GOOD_ENV = {
    "GITHUB_REPOSITORY": REPOSITORY,
    "GITHUB_REF": BRANCH,
    "GITHUB_EVENT_NAME": "push",
    "GITHUB_RUN_ID": "12345",
    "EXPECTED_HEAD": "a" * 40,
    "CHECKED_OUT_HEAD": "a" * 40,
}


def simulated_model(prompt):
    return "def add_numbers(left, right):\n    return left + right\n", {
        "model_revision": MODEL_REVISION,
        "model_loaded_and_generated": True,
        "generated_token_count": 20,
    }


class ProbeTests(unittest.TestCase):
    def test_valid_generated_code(self):
        self.assertEqual(
            normalize_candidate("def add_numbers(left, right):\n    return left + right"),
            "def add_numbers(left, right):\n    return left + right\n",
        )

    def test_fenced_generated_code(self):
        fence = chr(96) * 3
        self.assertTrue(normalize_candidate(
            fence + "python\ndef add_numbers(left, right):\n    return left + right\n" + fence
        ).startswith("def add_numbers"))

    def test_reject_unsafe_or_wrong_code(self):
        snippets = [
            "import os\ndef add_numbers(left,right):\n return left + right",
            "def add_numbers(left,right):\n import os\n return left + right",
            "def add_numbers(left,right):\n return left - right",
            "def add_numbers(left,right):\n return __import__('os').system('id')",
            "def different(left,right):\n return left + right",
            "def add_numbers(left,right):\n return left + right\nprint('extra')",
            "@staticmethod\ndef add_numbers(left,right):\n return left + right",
        ]
        for snippet in snippets:
            with self.subTest(snippet=snippet), self.assertRaises(ProbeBlocked):
                normalize_candidate(snippet)

    def test_exact_repo_branch_head_required(self):
        for field, value in [
            ("GITHUB_REPOSITORY", "other/repo"),
            ("GITHUB_REF", "refs/heads/main"),
            ("EXPECTED_HEAD", "main"),
            ("CHECKED_OUT_HEAD", "b" * 40),
            ("GITHUB_EVENT_NAME", "pull_request"),
        ]:
            with self.subTest(field=field), self.assertRaises(ProbeBlocked):
                validate_environment({**GOOD_ENV, field: value})

    def test_offline_receipt_never_claims_autonomous_development(self):
        with TemporaryDirectory() as root:
            directory = Path(root) / "proof"
            receipt = run_probe(GOOD_ENV, directory, simulated_model)
            self.assertEqual(json.loads((directory / "receipt.json").read_text()), receipt)
            self.assertFalse(receipt["github_writes"])
            self.assertFalse(receipt["pr_created"])
            self.assertEqual(receipt["autonomous_development_e2e"], "NOT_PROVEN")

    def test_missing_inference_evidence_rejected(self):
        with TemporaryDirectory() as root:
            with self.assertRaises(ProbeBlocked):
                run_probe(GOOD_ENV, Path(root) / "proof", lambda _: ("", {}))

    def test_existing_output_path_rejected(self):
        with TemporaryDirectory() as root:
            with self.assertRaises(ProbeBlocked):
                run_probe(GOOD_ENV, root, simulated_model)


if __name__ == "__main__":
    unittest.main()
