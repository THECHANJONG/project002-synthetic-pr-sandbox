"""Mocked negative controls for read-only API/ZIP binding (not a live E2E)."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.attest_live_patch_artifact import API, WORKFLOW, attest
from scripts.prepare_patch_artifact import CODE, PROJECT_REPO, TARGET
from scripts.validate_patch_promotion import InvalidPromotion

HEAD = "4bfc1d9052405bc0da4a2181149658d995e62b48"
RUN_ID = 41434610663
ARTIFACT_ID = 13135577198


class LiveAttestationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.checkout = Path(self.temp.name)
        target = self.checkout / TARGET
        target.parent.mkdir()
        target.write_text(CODE.replace("not deployed or merged", "already merged"))
        self.receipt = {
            "schema_version": 1, "project_id": "PROJECT_002_SYNTHETIC",
            "proof_scope": "DETERMINISTIC_PATCH_ARTIFACT_ONLY",
            "repository": PROJECT_REPO, "event": "push",
            "head_sha": HEAD, "run_id": RUN_ID, "run_attempt": 1,
            "target": TARGET, "candidate_status": "ALREADY_PRESENT",
            "patch_sha256": hashlib.sha256(b"").hexdigest(), "patch_bytes": 0,
            "github_pr_opened": False, "github_main_merged": False,
            "scheduler_invocation_attestation": "UNAVAILABLE",
            "independent_ai_cold_start": "NOT_PROVEN",
            "remote_cas_lease_fencing": "NOT_PROVEN",
        }
        self.run = {
            "id": RUN_ID, "run_attempt": 1, "event": "push",
            "repository": {"full_name": PROJECT_REPO},
            "path": WORKFLOW, "head_branch": "main", "head_sha": HEAD,
            "status": "completed", "conclusion": "success",
        }
        self.artifact = {
            "id": ARTIFACT_ID,
            "name": f"phase1-bounded-patch-{RUN_ID}-1",
            "expired": False,
            "archive_download_url": API + f"/actions/artifacts/{ARTIFACT_ID}/zip",
            "workflow_run": {"id": RUN_ID, "head_sha": HEAD, "head_branch": "main"},
        }
        self.refresh_zip()

    def refresh_zip(self, patch=b""):
        self.receipt["patch_sha256"] = hashlib.sha256(patch).hexdigest()
        self.receipt["patch_bytes"] = len(patch)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("receipt.json", json.dumps(self.receipt))
            z.writestr("candidate.patch", patch)
        self.zip = buf.getvalue()
        self.artifact["digest"] = "sha256:" + hashlib.sha256(self.zip).hexdigest()

    def verify(self, *, head_get=None):
        def json_get(url):
            if url == API + f"/actions/runs/{RUN_ID}":
                return self.run
            if url == API + f"/actions/runs/{RUN_ID}/artifacts":
                return {"artifacts": [self.artifact]}
            raise AssertionError("unexpected API URL: " + url)
        return attest(RUN_ID, ARTIFACT_ID, expected_head=HEAD,
                      checkout_root=self.checkout, json_get=json_get,
                      zip_get=lambda url: self.zip,
                      head_get=head_get or (lambda root: HEAD))

    def rejected(self):
        with self.assertRaises(InvalidPromotion):
            self.verify()

    def test_valid_already_present_is_not_pr_eligible(self):
        result = self.verify()
        self.assertEqual(result["github_run_api_attestation"],
                         "VERIFIED_METADATA_AND_ARCHIVE")
        self.assertFalse(result["pr_eligible_after_independent_run_check"])
        self.assertEqual(result["scheduler_invocation_attestation"], "UNAVAILABLE")
        self.assertEqual(result["ai_authored_pr_merge"], "NOT_PROVEN")

    def test_wrong_checkout_head(self):
        self.rejected_checkout = lambda root: "b" * 40
        with self.assertRaises(InvalidPromotion):
            self.verify(head_get=self.rejected_checkout)

    def test_failed_run(self):
        self.run["conclusion"] = "failure"
        self.rejected()

    def test_pending_run(self):
        self.run["status"] = "in_progress"
        self.rejected()

    def test_wrong_run_attempt(self):
        self.run["run_attempt"] = 2
        self.rejected()

    def test_wrong_run_repository(self):
        self.run["repository"]["full_name"] = "other/repo"
        self.rejected()

    def test_wrong_workflow(self):
        self.run["path"] = ".github/workflows/other.yml"
        self.rejected()

    def test_wrong_run_sha(self):
        self.run["head_sha"] = "b" * 40
        self.rejected()

    def test_expired_artifact(self):
        self.artifact["expired"] = True
        self.rejected()

    def test_wrong_artifact_sha(self):
        self.artifact["workflow_run"]["head_sha"] = "b" * 40
        self.rejected()

    def test_wrong_archive_url(self):
        self.artifact["archive_download_url"] = "https://evil.example/zip"
        self.rejected()

    def test_zip_digest_mismatch(self):
        self.zip += b"tamper"
        self.rejected()

    def test_duplicate_zip_member(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("receipt.json", json.dumps(self.receipt))
            z.writestr("candidate.patch", b"")
            z.writestr("candidate.patch", b"")
        self.zip = buf.getvalue()
        self.artifact["digest"] = "sha256:" + hashlib.sha256(self.zip).hexdigest()
        self.rejected()

    def test_receipt_event_mismatch(self):
        self.receipt["event"] = "pull_request"
        self.refresh_zip()
        self.rejected()

    def test_receipt_run_id_mismatch(self):
        self.receipt["run_id"] += 1
        self.refresh_zip()
        self.rejected()

    def test_receipt_duplicate_json_key(self):
        buf = io.BytesIO()
        raw = json.dumps(self.receipt).replace('"run_id": ', '"run_id": 1, "run_id": ', 1)
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("receipt.json", raw)
            z.writestr("candidate.patch", b"")
        self.zip = buf.getvalue()
        self.artifact["digest"] = "sha256:" + hashlib.sha256(self.zip).hexdigest()
        self.rejected()

    def test_nonfinite_artifact_id(self):
        self.artifact["id"] = True
        self.rejected()


if __name__ == "__main__":
    unittest.main()
