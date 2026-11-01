"""Negative controls for two same-name immutable artifact creations."""
import unittest
from scripts.verify_artifact_claim import InvalidArtifactClaim, verify_claim

HEAD = "a" * 40
RUN = "41310000000"
A = {"worker": "host-a", "head_sha": HEAD, "hostname": "runner-a", "boot_id": "5d1f7426-7f15-49e2-9f3a-b69b8c100001", "claim_outcome": "success", "artifact_id": "13085489154"}
B = {"worker": "host-b", "head_sha": HEAD, "hostname": "runner-b", "boot_id": "5d1f7426-7f15-49e2-9f3a-b69b8c100002", "claim_outcome": "success", "artifact_id": "13086058057"}
BASE = {"schema_version": 1, "project_id": "PROJECT_002_SYNTHETIC", "claim_type": "IMMUTABLE_SINGLE_CREATE", "head_sha": HEAD, "run_id": RUN}
ARTS = {"host-a": {**BASE, "worker": "host-a", "boot_id": A["boot_id"]},
        "host-b": {**BASE, "worker": "host-b", "boot_id": B["boot_id"]}}


class ArtifactCounterexampleTests(unittest.TestCase):
    def test_two_distinct_artifacts_and_boots(self):
        result = verify_claim(A, B, ARTS, HEAD, RUN)
        self.assertEqual(result["result"], "TWO_DISTINCT_ARTIFACT_IDS_CREATED_AND_READ_BACK")
        self.assertFalse(result["artifact_name_is_safe_lock"])
        self.assertEqual(result["mutable_shared_cas"], "NOT_PROVEN")

    def test_single_success_is_not_a_duplicate_counterexample(self):
        self.reject(A, {**B, "claim_outcome": "failure"}, ARTS)

    def test_missing_id_rejected(self):
        self.reject(A, {**B, "artifact_id": ""}, ARTS)

    def test_same_id_rejected(self):
        self.reject(A, {**B, "artifact_id": A["artifact_id"]}, ARTS)

    def test_same_boot_rejected(self):
        self.reject(A, {**B, "boot_id": A["boot_id"]}, ARTS)

    def test_wrong_head_rejected(self):
        self.reject(A, {**B, "head_sha": "b" * 40}, ARTS)

    def test_wrong_artifact_owner_rejected(self):
        self.reject(A, B, {**ARTS, "host-a": {**ARTS["host-a"], "worker": "host-b"}})

    def test_wrong_artifact_boot_rejected(self):
        self.reject(A, B, {**ARTS, "host-b": {**ARTS["host-b"], "boot_id": A["boot_id"]}})

    def test_wrong_artifact_run_rejected(self):
        self.reject(A, B, {**ARTS, "host-a": {**ARTS["host-a"], "run_id": "123"}})

    def test_bool_schema_version_rejected(self):
        self.reject(A, B, {**ARTS, "host-a": {**ARTS["host-a"], "schema_version": True}})

    def test_unexpected_schema_rejected(self):
        self.reject(A, B, {**ARTS, "host-b": {**ARTS["host-b"], "authority": "production"}})

    def test_wrong_project_rejected(self):
        self.reject(A, B, {**ARTS, "host-a": {**ARTS["host-a"], "project_id": "PROJECT_002"}})

    def test_missing_artifact_rejected(self):
        self.reject(A, B, {"host-a": ARTS["host-a"]})

    def test_swapped_worker_rejected(self):
        self.reject({**A, "worker": "host-b"}, B, ARTS)

    def test_zero_run_id_rejected(self):
        with self.assertRaises(InvalidArtifactClaim):
            verify_claim(A, B, ARTS, HEAD, "0")

    def reject(self, a, b, artifacts):
        with self.assertRaises(InvalidArtifactClaim):
            verify_claim(a, b, artifacts, HEAD, RUN)


if __name__ == "__main__":
    unittest.main()
