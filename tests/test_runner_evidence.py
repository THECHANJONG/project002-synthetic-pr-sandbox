import unittest

from scripts.verify_runner_evidence import InvalidRunnerEvidence, verify_two_hosts

HEAD = "a" * 40
A = {"head_sha": HEAD, "hostname": "runner-a", "boot_id": "5d1f7426-7f15-49e2-9f3a-b69b8c100001"}
B = {"head_sha": HEAD, "hostname": "runner-b", "boot_id": "5d1f7426-7f15-49e2-9f3a-b69b8c100002"}


class RunnerEvidenceTests(unittest.TestCase):
    def test_two_distinct_boots_pass(self):
        result = verify_two_hosts(A, B, HEAD)
        self.assertEqual(result["result"], "TWO_DISTINCT_LINUX_BOOT_IDS_VERIFIED")
        self.assertEqual(result["shared_durable_cas"], "NOT_PROVEN")

    def test_same_boot_rejected_even_with_distinct_hostnames(self):
        with self.assertRaises(InvalidRunnerEvidence):
            verify_two_hosts(A, {**B, "boot_id": A["boot_id"]}, HEAD)

    def test_wrong_head_rejected(self):
        with self.assertRaises(InvalidRunnerEvidence):
            verify_two_hosts(A, {**B, "head_sha": "b" * 40}, HEAD)

    def test_short_expected_sha_rejected(self):
        with self.assertRaises(InvalidRunnerEvidence):
            verify_two_hosts(A, B, "a" * 7)

    def test_invalid_hostname_rejected(self):
        with self.assertRaises(InvalidRunnerEvidence):
            verify_two_hosts({**A, "hostname": "bad name"}, B, HEAD)

    def test_invalid_boot_rejected(self):
        with self.assertRaises(InvalidRunnerEvidence):
            verify_two_hosts(A, {**B, "boot_id": "not-a-uuid"}, HEAD)

    def test_zero_boot_rejected(self):
        with self.assertRaises(InvalidRunnerEvidence):
            verify_two_hosts(A, {**B, "boot_id": "00000000-0000-0000-0000-000000000000"}, HEAD)

    def test_non_object_rejected(self):
        with self.assertRaises(InvalidRunnerEvidence):
            verify_two_hosts(None, B, HEAD)


if __name__ == "__main__":
    unittest.main()
