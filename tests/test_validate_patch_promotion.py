"""Offline artifact promotion negative controls; not remote run authentication."""
import difflib
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_patch_artifact import CODE, PROJECT_REPO, TARGET
from scripts.validate_patch_promotion import validate_artifact, InvalidPromotion, main

HEAD = "a" * 40
RUN = 41400000000


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.artifact = self.root / "artifact"
        self.artifact.mkdir()
        self.patch = "".join(difflib.unified_diff(
            [], CODE.splitlines(keepends=True), fromfile="/dev/null",
            tofile="b/" + TARGET)).encode()
        self.receipt = dict(schema_version=1, project_id="PROJECT_002_SYNTHETIC",
            proof_scope="DETERMINISTIC_PATCH_ARTIFACT_ONLY",
            repository=PROJECT_REPO, event="push", head_sha=HEAD,
            run_id=RUN, run_attempt=1, target=TARGET,
            candidate_status="CREATE_ONLY", patch_sha256="", patch_bytes=0,
            github_pr_opened=False, github_main_merged=False,
            scheduler_invocation_attestation="UNAVAILABLE",
            independent_ai_cold_start="NOT_PROVEN",
            remote_cas_lease_fencing="NOT_PROVEN")
        self.write()

    def write(self):
        self.receipt["patch_sha256"] = hashlib.sha256(self.patch).hexdigest()
        self.receipt["patch_bytes"] = len(self.patch)
        (self.artifact / "receipt.json").write_text(json.dumps(self.receipt))
        (self.artifact / "candidate.patch").write_bytes(self.patch)

    def verify(self, **kw):
        return validate_artifact(self.artifact, expected_head=kw.get("head", HEAD),
            expected_run_id=kw.get("run", RUN), expected_attempt=kw.get("attempt", 1),
            checkout_root=self.checkout)

    def rejected(self):
        with self.assertRaises(InvalidPromotion):
            self.verify()

    def test_valid_create_only_offline(self):
        result = self.verify()
        self.assertEqual("VERIFIED", result["offline_consistency"])
        self.assertEqual("NOT_CHECKED", result["github_run_api_attestation"])
        self.assertTrue(result["pr_eligible_after_independent_run_check"])

    def test_valid_already_present_no_patch(self):
        target = self.checkout / TARGET
        target.parent.mkdir()
        target.write_text(CODE.replace("# Synthetic bounded code candidate; not deployed or merged.",
            "# Already merged"))
        self.receipt["candidate_status"] = "ALREADY_PRESENT"
        self.patch = b""
        self.write()
        self.assertFalse(self.verify()["pr_eligible_after_independent_run_check"])

    def test_stale_run_rejected(self):
        with self.assertRaises(InvalidPromotion):
            self.verify(run=RUN + 1)

    def test_stale_head_rejected(self):
        with self.assertRaises(InvalidPromotion):
            self.verify(head="b" * 40)

    def test_wrong_attempt_rejected(self):
        with self.assertRaises(InvalidPromotion):
            self.verify(attempt=2)

    def test_bool_run_id_rejected(self):
        self.receipt["run_id"] = True
        self.write()
        self.rejected()

    def test_tampered_patch_with_recomputed_hash_rejected(self):
        self.patch = self.patch.replace(b"github-actions-readonly", b"evil-executor")
        self.write()
        self.rejected()

    def test_bad_hash_rejected(self):
        self.receipt["patch_sha256"] = "0" * 64
        (self.artifact / "receipt.json").write_text(json.dumps(self.receipt))
        self.rejected()

    def test_unexpected_artifact_file_rejected(self):
        (self.artifact / "extra.txt").write_text("unexpected")
        self.rejected()

    def test_symlink_member_rejected(self):
        (self.artifact / "candidate.patch").unlink()
        (self.artifact / "candidate.patch").symlink_to(self.artifact / "receipt.json")
        self.rejected()

    def test_symlink_artifact_directory_rejected(self):
        link = self.root / "link"
        link.symlink_to(self.artifact, target_is_directory=True)
        with self.assertRaises(InvalidPromotion):
            validate_artifact(link, expected_head=HEAD, expected_run_id=RUN,
                              expected_attempt=1, checkout_root=self.checkout)

    def test_target_now_exists_rejected(self):
        target = self.checkout / TARGET
        target.parent.mkdir()
        target.write_text(CODE)
        self.rejected()

    def test_parent_symlink_rejected(self):
        (self.checkout / "generated").symlink_to(self.root, target_is_directory=True)
        self.rejected()

    def test_parent_regular_file_rejected(self):
        (self.checkout / "generated").write_text("not a directory")
        self.rejected()

    def test_dangling_target_symlink_rejected(self):
        parent = self.checkout / "generated"
        parent.mkdir()
        (parent / "phase1_worker_probe.py").symlink_to(self.root / "missing")
        self.rejected()

    def test_duplicate_json_key_rejected(self):
        p = self.artifact / "receipt.json"
        p.write_text(p.read_text().replace('"run_id": ', '"run_id": 1, "run_id": ', 1))
        self.rejected()

    def test_nonfinite_json_rejected(self):
        p = self.artifact / "receipt.json"
        p.write_text(p.read_text().replace('"run_id": ', '"run_id": NaN, "shadow": ', 1))
        self.rejected()

    def test_misleading_success_flag_rejected(self):
        self.receipt["github_main_merged"] = True
        self.write()
        self.rejected()

    def test_extra_receipt_key_rejected(self):
        self.receipt["unverified_claim"] = "PROVEN"
        self.write()
        self.rejected()

    def test_wrong_status_rejected(self):
        self.receipt["candidate_status"] = "MERGED"
        self.write()
        self.rejected()

    def test_oversize_patch_rejected(self):
        self.patch = b"x" * 4097
        self.write()
        self.rejected()

    def test_existing_different_code_rejected(self):
        target = self.checkout / TARGET
        target.parent.mkdir()
        target.write_text(CODE.replace("github-actions-readonly", "changed"))
        self.receipt["candidate_status"] = "ALREADY_PRESENT"
        self.patch = b""
        self.write()
        self.rejected()

    def test_cli_offline_verdict(self):
        from contextlib import redirect_stdout
        from io import StringIO
        output = StringIO()
        with redirect_stdout(output):
            main(["--artifact", str(self.artifact), "--checkout", str(self.checkout),
                  "--expected-head", HEAD, "--run-id", str(RUN), "--attempt", "1"])
        self.assertEqual("VERIFIED", json.loads(output.getvalue())["offline_consistency"])


if __name__ == "__main__":
    unittest.main()
