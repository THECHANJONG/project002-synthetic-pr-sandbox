"""Fail-closed negative controls for real cross-host immutable artifact race."""
import unittest

from scripts.verify_artifact_claim import InvalidArtifactClaim, verify_claim

HEAD = "a" * 40
RUN = "41310000000"
A = {"worker": "host-a", "head_sha": HEAD, "hostname": "runner-a", "boot_id": "5d1f7426-7f15-49e2-9f3a-b69b8c100001", "claim_outcome": "success"}
B = {"worker": "host-b", "head_sha": HEAD, "hostname": "runner-b", "boot_id": "5d1f7426-7f15-49e2-9f3a-b69b8c100002", "claim_outcome": "failure"}
CLAIM = {"schema_version": 1, "project_id": "PROJECT_002_SYNTHETIC", "claim_type": "IMMUTABLE_SINGLE_CREATE", "worker": "host-a", "head_sha": HEAD, "boot_id": A["boot_id"], "run_id": RUN}


class ArtifactClaimTests(unittest.TestCase):
    def test_one_winner_and_distinct_boots(self):
        result = verify_claim(A, B, CLAIM, HEAD, RUN)
        self.assertEqual(result["winning_worker"], "host-a")
        self.assertEqual(result["mutable_shared_cas"], "NOT_PROVEN")
        self.assertEqual(result["scheduler_invocation_attestation"], "UNAVAILABLE")

    def test_other_worker_can_win(self):
        a = {**A, "claim_outcome": "failure"}
        b = {**B, "claim_outcome": "success"}
        claim = {**CLAIM, "worker": "host-b", "boot_id": B["boot_id"]}
        self.assertEqual(verify_claim(a, b, claim, HEAD, RUN)["winning_worker"], "host-b")

    def test_two_winners_rejected(self):
        self.reject(A, {**B, "claim_outcome": "success"}, CLAIM)

    def test_zero_winners_rejected(self):
        self.reject({**A, "claim_outcome": "failure"}, B, CLAIM)

    def test_same_boot_rejected(self):
        self.reject(A, {**B, "boot_id": A["boot_id"]}, CLAIM)

    def test_wrong_head_rejected(self):
        self.reject(A, {**B, "head_sha": "b" * 40}, CLAIM)

    def test_wrong_artifact_owner_rejected(self):
        self.reject(A, B, {**CLAIM, "worker": "host-b"})

    def test_wrong_artifact_boot_rejected(self):
        self.reject(A, B, {**CLAIM, "boot_id": B["boot_id"]})

    def test_wrong_run_rejected(self):
        self.reject(A, B, {**CLAIM, "run_id": "123"})

    def test_boolean_version_rejected(self):
        self.reject(A, B, {**CLAIM, "schema_version": True})

    def test_unknown_schema_field_rejected(self):
        self.reject(A, B, {**CLAIM, "authority": "production"})

    def test_wrong_project_rejected(self):
        self.reject(A, B, {**CLAIM, "project_id": "PROJECT_002"})

    def test_unexpected_outcome_rejected(self):
        self.reject(A, {**B, "claim_outcome": "cancelled"}, CLAIM)

    def test_swapped_worker_rejected(self):
        self.reject({**A, "worker": "host-b"}, B, CLAIM)

    def test_invalid_run_id_rejected(self):
        with self.assertRaises(InvalidArtifactClaim):
            verify_claim(A, B, CLAIM, HEAD, "0")

    def reject(self, a, b, claim):
        with self.assertRaises(InvalidArtifactClaim):
            verify_claim(a, b, claim, HEAD, RUN)


if __name__ == "__main__":
    unittest.main()
