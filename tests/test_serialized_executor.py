"""Positive and negative controls for the bounded Actions serialized executor."""
import unittest
from pathlib import Path

from scripts.verify_serialized_executor import InvalidExecutorIdentity, verify_identity

SHA = "a" * 40
WF = Path(__file__).resolve().parents[1] / ".github/workflows/phase1-serialized-executor-readonly.yml"


def fixture():
    return {
        "GITHUB_REPOSITORY": "THECHANJONG/project002-synthetic-pr-sandbox",
        "GITHUB_WORKFLOW": "phase1-serialized-executor-readonly",
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_RUN_ID": "41320000000",
        "GITHUB_RUN_ATTEMPT": "1",
        "EXPECTED_HEAD": SHA,
        "CHECKED_OUT_HEAD": SHA,
    }


class SerializedExecutorTests(unittest.TestCase):
    def test_valid_exact_head_is_read_only(self):
        result = verify_identity(fixture())
        self.assertEqual(result["exact_head"], SHA)
        self.assertFalse(result["github_concurrency_is_durable_queue"])
        self.assertEqual(result["mutable_authority"], "NOT_GRANTED")

    def test_push_trigger(self):
        env = fixture()
        env["GITHUB_EVENT_NAME"] = "push"
        self.assertEqual(verify_identity(env)["status"], "READ_ONLY_IDENTITY_PREFLIGHT_VERIFIED")

    def test_rejects_wrong_repository(self):
        self.reject("GITHUB_REPOSITORY", "other/repo")

    def test_rejects_wrong_workflow(self):
        self.reject("GITHUB_WORKFLOW", "other")

    def test_rejects_manual_trigger(self):
        self.reject("GITHUB_EVENT_NAME", "workflow_dispatch")

    def test_rejects_bad_run_id(self):
        self.reject("GITHUB_RUN_ID", "0")

    def test_rejects_type_coerced_run_id(self):
        self.reject("GITHUB_RUN_ID", 1)

    def test_rejects_bad_attempt(self):
        self.reject("GITHUB_RUN_ATTEMPT", "01")

    def test_rejects_mismatched_checkout(self):
        self.reject("CHECKED_OUT_HEAD", "b" * 40)

    def test_rejects_uppercase_sha(self):
        self.reject("EXPECTED_HEAD", "A" * 40)

    def test_rejects_missing_head(self):
        self.reject("EXPECTED_HEAD", None)

    def test_rejects_nonobject(self):
        with self.assertRaises(InvalidExecutorIdentity):
            verify_identity([])

    def reject(self, key, value):
        env = fixture()
        env[key] = value
        with self.assertRaises(InvalidExecutorIdentity):
            verify_identity(env)

    def test_workflow_contract(self):
        content = WF.read_text(encoding="utf-8")
        for required in (
            "permissions:\\n  contents: read",
            "group: project002-synthetic-serialized-executor-readonly",
            "cancel-in-progress: false",
            "ref: ${{ github.event.pull_request.head.sha || github.sha }}",
            "persist-credentials: false",
            'test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"',
            "CHECKED_OUT_HEAD=",
            "python3 -m scripts.verify_serialized_executor",
            "GITHUB_CONCURRENCY_DURABLE_QUEUE=NOT_PROVEN",
            "SHARED_REMOTE_CAS_LEASE_FENCING=NOT_PROVEN",
            "MUTABLE_AUTHORITY=NOT_GRANTED",
        ):
            self.assertIn(required.replace("\\n","\n"), content)
        self.assertNotIn("contents: write", content)
        self.assertNotIn("secrets.", content)
        self.assertNotIn("workflow_dispatch:", content)


if __name__ == "__main__":
    unittest.main()
