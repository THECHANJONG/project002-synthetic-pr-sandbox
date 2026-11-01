"""Fail-closed controls: same-name artifact uploads are not a lock."""
import unittest
from scripts.verify_artifact_claim import InvalidArtifactClaim, verify_claim

HEAD = "a" * 40
RUN = "41310000000"
A = {"worker": "host-a", "head_sha": HEAD, "hostname": "runner-a", "boot_id": "5d1f7426-7f15-49e2-9f3a-b69b8c100001", "claim_outcome": "success", "artifact_id": "13085489154"}
B = {"worker": "host-b", "head_sha": HEAD, "hostname": "runner-b", "boot_id": "5d1f7426-7f15-49e2-9f3a-b69b8c100002", "claim_outcome": "success", "artifact_id": "13086058057"}
CLAIM = {"schema_version": 1, "project_id": "PROJECT_002_SYNTHETIC", "claim_type": "IMMUTABLE_SINGLE_CREATE", "head_sha": HEAD, "run_id": RUN, "worker": "host-a", "boot_id": A["boot_id"]}


class ArtifactCounterexampleTests(unittest.TestCase):
    def test_two_uploads_one_readback(self):
        result = verify_claim(A, B, CLAIM, HEAD, RUN)
        self.assertEqual(result["result"], "TWO_SAME_NAME_UPLOADS_ONE_ARTIFACT_READ_BACK")
        self.assertFalse(result["artifact_name_is_safe_lock"])
        self.assertEqual(result["second_artifact_readback"], "NOT_VERIFIED_IN_WORKFLOW")

    def test_other_worker_readback(self):
        result = verify_claim(A, B, {**CLAIM, "worker": "host-b", "boot_id": B["boot_id"]}, HEAD, RUN)
        self.assertEqual(result["downloaded_worker"], "host-b")

    def test_single_success_not_counterexample(self):
        self.reject(A, {**B, "claim_outcome": "failure"}, CLAIM)

    def test_missing_id(self):
        self.reject(A, {**B, "artifact_id": ""}, CLAIM)

    def test_same_id(self):
        self.reject(A, {**B, "artifact_id": A["artifact_id"]}, CLAIM)

    def test_same_boot(self):
        self.reject(A, {**B, "boot_id": A["boot_id"]}, CLAIM)

    def test_wrong_head(self):
        self.reject(A, {**B, "head_sha": "b" * 40}, CLAIM)

    def test_unknown_artifact_owner(self):
        self.reject(A, B, {**CLAIM, "worker": "host-c"})

    def test_wrong_artifact_boot(self):
        self.reject(A, B, {**CLAIM, "boot_id": B["boot_id"]})

    def test_wrong_run(self):
        self.reject(A, B, {**CLAIM, "run_id": "123"})

    def test_bool_schema_version(self):
        self.reject(A, B, {**CLAIM, "schema_version": True})

    def test_extra_schema_field(self):
        self.reject(A, B, {**CLAIM, "authority": "production"})

    def test_wrong_project(self):
        self.reject(A, B, {**CLAIM, "project_id": "PROJECT_002"})

    def test_swapped_worker(self):
        self.reject({**A, "worker": "host-b"}, B, CLAIM)

    def test_invalid_run_id(self):
        with self.assertRaises(InvalidArtifactClaim):
            verify_claim(A, B, CLAIM, HEAD, "0")

    def reject(self, a, b, claim):
        with self.assertRaises(InvalidArtifactClaim):
            verify_claim(a, b, claim, HEAD, RUN)


if __name__ == "__main__":
    unittest.main()
