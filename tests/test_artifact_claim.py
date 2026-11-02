"""Fail-closed controls: same-name artifact uploads are not a lock."""
import unittest
from scripts.verify_artifact_claim import InvalidArtifactClaim, verify_claim, verify_inventory

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


    def sample_inventory(self):
        return {"total_count": 2, "artifacts": [
            {"id": int(worker["artifact_id"]),
             "name": "phase1-synthetic-single-create", "expired": False,
             "workflow_run": {"id": int(RUN), "repository_id": 123456,
                              "head_repository_id": 123456,
                              "head_branch": "main", "head_sha": HEAD}}
            for worker in (A, B)
        ]}

    def test_live_inventory_binds_both_artifacts_without_claiming_cas(self):
        result = verify_inventory(A, B, self.sample_inventory(), HEAD, RUN)
        self.assertEqual(result["github_artifact_inventory_crosscheck"], "VERIFIED")
        self.assertEqual(result["second_artifact_readback"], "METADATA_ONLY_VERIFIED")
        self.assertFalse(result["artifact_name_is_safe_lock"])
        self.assertEqual(result["shared_durable_cas"], "NOT_PROVEN")

    def test_rejects_incomplete_inventory(self):
        inv = self.sample_inventory()
        inv["artifacts"].pop()
        self.reject_inventory(inv)

    def test_rejects_forged_total_count(self):
        inv = self.sample_inventory()
        inv["total_count"] = True
        self.reject_inventory(inv)

    def test_rejects_unknown_artifact_id(self):
        inv = self.sample_inventory()
        inv["artifacts"][0]["id"] += 1
        self.reject_inventory(inv)

    def test_rejects_duplicate_artifact_id(self):
        inv = self.sample_inventory()
        inv["artifacts"][1]["id"] = inv["artifacts"][0]["id"]
        self.reject_inventory(inv)

    def test_rejects_wrong_name(self):
        inv = self.sample_inventory()
        inv["artifacts"][0]["name"] = "other"
        self.reject_inventory(inv)

    def test_rejects_expired_artifact(self):
        inv = self.sample_inventory()
        inv["artifacts"][1]["expired"] = True
        self.reject_inventory(inv)

    def test_rejects_other_run(self):
        inv = self.sample_inventory()
        inv["artifacts"][0]["workflow_run"]["id"] += 1
        self.reject_inventory(inv)

    def test_rejects_other_head(self):
        inv = self.sample_inventory()
        inv["artifacts"][0]["workflow_run"]["head_sha"] = "b" * 40
        self.reject_inventory(inv)

    def test_rejects_other_branch(self):
        inv = self.sample_inventory()
        inv["artifacts"][0]["workflow_run"]["head_branch"] = "test"
        self.reject_inventory(inv)

    def test_rejects_fork_repository_mismatch(self):
        inv = self.sample_inventory()
        inv["artifacts"][0]["workflow_run"]["head_repository_id"] = 999
        self.reject_inventory(inv)

    def test_rejects_cross_repository_inventory(self):
        inv = self.sample_inventory()
        inv["artifacts"][0]["workflow_run"]["repository_id"] = 999
        inv["artifacts"][0]["workflow_run"]["head_repository_id"] = 999
        self.reject_inventory(inv)

    def test_rejects_bool_artifact_id(self):
        inv = self.sample_inventory()
        inv["artifacts"][0]["id"] = True
        self.reject_inventory(inv)

    def test_rejects_missing_origin(self):
        inv = self.sample_inventory()
        del inv["artifacts"][0]["workflow_run"]
        self.reject_inventory(inv)

    def reject_inventory(self, inventory):
        with self.assertRaises(InvalidArtifactClaim):
            verify_inventory(A, B, inventory, HEAD, RUN)

    def reject(self, a, b, claim):
        with self.assertRaises(InvalidArtifactClaim):
            verify_claim(a, b, claim, HEAD, RUN)


if __name__ == "__main__":
    unittest.main()
