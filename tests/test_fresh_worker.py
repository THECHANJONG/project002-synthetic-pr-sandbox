"""Negative controls for a context-free synthetic handoff; no live AI proof."""
import json
import unittest
from pathlib import Path
from scripts.verify_fresh_worker import MANIFEST, UnsafeHandoff, verify_environment, verify_manifest

SHA = "a" * 40


def valid_env(event="push"):
    return {
        "GITHUB_REPOSITORY": "THECHANJONG/project002-synthetic-pr-sandbox",
        "GITHUB_WORKFLOW": "phase1-fresh-worker-readonly",
        "GITHUB_EVENT_NAME": event,
        "REMOTE_REF": "refs/heads/main" if event == "push" else "refs/pull/10/head",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "EXPECTED_HEAD": SHA,
        "CHECKED_OUT_HEAD": SHA,
        "REMOTE_HEAD": SHA,
    }


class FreshWorkerTests(unittest.TestCase):
    def test_checked_in_entrypoint(self):
        source = Path(__file__).resolve().parents[1] / "handoff/SYNTHETIC_ENTRYPOINT.json"
        self.assertEqual(MANIFEST, verify_manifest(source.read_text(encoding="utf-8")))

    def test_push_reconstruction(self):
        self.assertEqual("FRESH_PROCESS_READ_ONLY_RECONSTRUCTION", verify_environment(valid_env())["status"])

    def test_pr_reconstruction(self):
        self.assertEqual("refs/pull/10/head", verify_environment(valid_env("pull_request"))["remote_ref"])

    def test_duplicate_key_rejected(self):
        with self.assertRaises(UnsafeHandoff):
            verify_manifest('{"schema_version":1,"schema_version":1}')

    def test_type_coercion_rejected(self):
        changed = dict(MANIFEST, schema_version=True)
        with self.assertRaises(UnsafeHandoff):
            verify_manifest(json.dumps(changed))

    def test_mutable_authority_rejected(self):
        changed = dict(MANIFEST, write_authorized=True)
        with self.assertRaises(UnsafeHandoff):
            verify_manifest(json.dumps(changed))

    def test_unknown_manifest_field_rejected(self):
        changed = dict(MANIFEST, invented="yes")
        with self.assertRaises(UnsafeHandoff):
            verify_manifest(json.dumps(changed))

    def test_invalid_json_rejected(self):
        with self.assertRaises(UnsafeHandoff):
            verify_manifest("{broken")

    def test_remote_head_drift_rejected(self):
        changed = valid_env()
        changed["REMOTE_HEAD"] = "b" * 40
        with self.assertRaises(UnsafeHandoff):
            verify_environment(changed)

    def test_checkout_head_drift_rejected(self):
        changed = valid_env()
        changed["CHECKED_OUT_HEAD"] = "b" * 40
        with self.assertRaises(UnsafeHandoff):
            verify_environment(changed)

    def test_pr_ref_swap_rejected(self):
        changed = valid_env("pull_request")
        changed["REMOTE_REF"] = "refs/heads/main"
        with self.assertRaises(UnsafeHandoff):
            verify_environment(changed)

    def test_unexpected_event_rejected(self):
        changed = valid_env()
        changed["GITHUB_EVENT_NAME"] = "workflow_dispatch"
        with self.assertRaises(UnsafeHandoff):
            verify_environment(changed)

    def test_numeric_id_type_rejected(self):
        changed = valid_env()
        changed["GITHUB_RUN_ID"] = 123
        with self.assertRaises(UnsafeHandoff):
            verify_environment(changed)

    def test_wrong_workflow_rejected(self):
        changed = valid_env()
        changed["GITHUB_WORKFLOW"] = "synthetic-ci"
        with self.assertRaises(UnsafeHandoff):
            verify_environment(changed)


class FreshWorkerWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[1] / ".github/workflows/phase1-fresh-worker-readonly.yml").read_text(encoding="utf-8")

    def test_workflow_read_only_and_pinned(self):
        self.assertIn("permissions:\n  contents: read\n", self.source)
        self.assertNotIn("contents: write", self.source)
        self.assertNotIn("secrets.", self.source)
        self.assertIn("persist-credentials: false", self.source)
        self.assertIn("actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683", self.source)
        self.assertIn("python3 -m scripts.verify_fresh_worker", self.source)

    def test_workflow_fails_closed_on_remote_drift(self):
        self.assertIn("set -euo pipefail", self.source)
        self.assertIn('git ls-remote origin "$REMOTE_REF"', self.source)
        self.assertIn('export CHECKED_OUT_HEAD REMOTE_HEAD', self.source)


if __name__ == "__main__":
    unittest.main()
