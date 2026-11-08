import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.candidate_promotion import promote


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)
        self.old = Path.cwd()
        os.chdir(self.cwd)
        self.addCleanup(os.chdir, self.old)
        self.candidate = self.cwd / "candidate.py"
        self.candidate.write_text("def answer():\n    return 42\n")
        self.receipt = self.cwd / "receipt.json"
        self.data = {
            "candidate_sha256": hashlib.sha256(self.candidate.read_bytes()).hexdigest(),
            "run_id": 42096325448,
            "source_repository": "THECHANJONG/project002-synthetic-pr-sandbox",
            "model_executed": True,
        }
        self.dest = self.cwd / "synthetic" / "model_candidate.py"

    def run_promotion(self):
        self.receipt.write_text(json.dumps(self.data))
        return promote(self.candidate, self.receipt, self.dest, 42096325448)

    def test_valid_candidate(self):
        self.assertEqual(self.run_promotion(), self.data["candidate_sha256"])
        self.assertEqual(self.dest.read_bytes(), self.candidate.read_bytes())

    def test_reject_modified_bytes(self):
        self.data["candidate_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.run_promotion()

    def test_reject_untrusted_run(self):
        self.data["run_id"] = 3
        with self.assertRaises(ValueError):
            self.run_promotion()

    def test_reject_unattested_model(self):
        self.data["model_executed"] = False
        with self.assertRaises(ValueError):
            self.run_promotion()

    def test_reject_wrong_repository(self):
        self.data["source_repository"] = "someone/private"
        with self.assertRaises(ValueError):
            self.run_promotion()

    def test_reject_executable_import(self):
        self.candidate.write_text("import os\n")
        self.data["candidate_sha256"] = hashlib.sha256(self.candidate.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            self.run_promotion()

    def test_reject_overwrite(self):
        self.dest.parent.mkdir()
        self.dest.write_text("preserve")
        with self.assertRaises(FileExistsError):
            self.run_promotion()
        self.assertEqual(self.dest.read_text(), "preserve")

    def test_reject_outside_fixture(self):
        self.dest = self.cwd / "outside" / "model_candidate.py"
        with self.assertRaises(ValueError):
            self.run_promotion()


if __name__ == "__main__":
    unittest.main()
