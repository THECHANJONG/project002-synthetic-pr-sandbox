import hashlib
import unittest
from candidate_provenance_gate import CandidateRejected, verify_candidate

SOURCE = b"def generated_value():\n    return 42\n"
HEAD = "a" * 40
def manifest(source=SOURCE):
    return {"run_id": "123", "head_sha": HEAD, "sha256": hashlib.sha256(source).hexdigest(), "path": "generated/candidate.py"}

class CandidateGateTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(verify_candidate(SOURCE, manifest(), expected_run_id=123, expected_head_sha=HEAD), SOURCE.decode())
    def test_digest_mismatch(self):
        with self.assertRaises(CandidateRejected):
            verify_candidate(SOURCE+b" ", manifest(), expected_run_id=123, expected_head_sha=HEAD)
    def test_run_mismatch(self):
        with self.assertRaises(CandidateRejected):
            verify_candidate(SOURCE, manifest(), expected_run_id=124, expected_head_sha=HEAD)
    def test_head_mismatch(self):
        with self.assertRaises(CandidateRejected):
            verify_candidate(SOURCE, manifest(), expected_run_id=123, expected_head_sha="b"*40)
    def test_path_escape(self):
        m=manifest(); m["path"]="../production.py"
        with self.assertRaises(CandidateRejected):
            verify_candidate(SOURCE, m, expected_run_id=123, expected_head_sha=HEAD)
    def test_side_effects(self):
        bad=b"import os\ndef generated_value():\n    return os.getcwd()\n"
        with self.assertRaises(CandidateRejected):
            verify_candidate(bad, manifest(bad), expected_run_id=123, expected_head_sha=HEAD)
    def test_expression_rejected(self):
        bad=b"def generated_value():\n    return 1 + 2\n"
        with self.assertRaises(CandidateRejected):
            verify_candidate(bad, manifest(bad), expected_run_id=123, expected_head_sha=HEAD)
    def test_manifest_extra_field(self):
        m=manifest();m["untrusted"]=True
        with self.assertRaises(CandidateRejected):
            verify_candidate(SOURCE,m,expected_run_id=123,expected_head_sha=HEAD)
if __name__ == "__main__":
    unittest.main()
