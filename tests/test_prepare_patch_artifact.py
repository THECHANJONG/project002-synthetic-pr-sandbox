"""Negative controls for read-only, bounded GitHub Actions patch preparation."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from scripts.prepare_patch_artifact import prepare, InvalidProvenance, TARGET

SHA = "a" * 40
ENV = {
    "GITHUB_REPOSITORY": "THECHANJONG/project002-synthetic-pr-sandbox",
    "EXPECTED_HEAD": SHA,
    "CHECKED_OUT_HEAD": SHA,
    "GITHUB_EVENT_NAME": "pull_request",
    "GITHUB_REF": "refs/pull/23/merge",
    "GITHUB_RUN_ID": "41399999999",
    "GITHUB_RUN_ATTEMPT": "1",
}


class PatchArtifactTests(unittest.TestCase):
    def test_patch_and_manifest_match_exact_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "artifact"
            receipt = prepare(dict(ENV), output_dir=root)
            patch = (root / "candidate.patch").read_bytes()
            self.assertEqual(hashlib.sha256(patch).hexdigest(), receipt["patch_sha256"])
            self.assertEqual(len(patch), receipt["patch_bytes"])
            self.assertIn("+++ b/" + TARGET, patch.decode())
            self.assertFalse(receipt["github_pr_opened"])
            self.assertFalse(receipt["github_main_merged"])
            self.assertEqual(receipt, json.loads((root / "receipt.json").read_text()))

    def test_main_push_accepted(self):
        env = dict(ENV, GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/main")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual("push", prepare(env, output_dir=Path(d)/"artifact")["event"])

    def test_rejects_mismatched_head(self):
        self.reject(CHECKED_OUT_HEAD="b" * 40)

    def test_rejects_wrong_repo(self):
        self.reject(GITHUB_REPOSITORY="THECHANJONG/ai-quality-control-system")

    def test_rejects_bad_sha(self):
        self.reject(EXPECTED_HEAD="abc", CHECKED_OUT_HEAD="abc")

    def test_rejects_untrusted_event(self):
        self.reject(GITHUB_EVENT_NAME="issue_comment")

    def test_rejects_pr_ref_spoof(self):
        self.reject(GITHUB_REF="refs/heads/main")

    def test_rejects_feature_push(self):
        self.reject(GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/test/example")

    def test_rejects_invalid_run_id(self):
        self.reject(GITHUB_RUN_ID="0")

    def test_rejects_invalid_attempt(self):
        self.reject(GITHUB_RUN_ATTEMPT="1;curl evil")

    def test_rejects_nonempty_artifact_directory_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "artifact"
            root.mkdir()
            (root / "receipt.json").write_text("protected")
            with self.assertRaises(InvalidProvenance):
                prepare(dict(ENV), output_dir=root)
            self.assertEqual("protected", (root / "receipt.json").read_text())

    def reject(self, **changes):
        env = dict(ENV, **changes)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "artifact"
            with self.assertRaises(InvalidProvenance):
                prepare(env, output_dir=root)
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
