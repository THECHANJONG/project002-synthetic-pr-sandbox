"""Guard the real Actions pre-upload validator, not remote artifact authentication."""
import re
from pathlib import Path
import unittest


WORKFLOW = (Path(__file__).resolve().parents[1] /
            ".github/workflows/phase1-bounded-patch-probe.yml")
GATE = "      - name: Fail closed on locally generated artifact before upload\n"
UPLOAD = "      - name: Upload immutable bounded patch and run receipt\n"
PREPARE = "python3 -m scripts.prepare_patch_artifact"
VALIDATE = "python3 -m scripts.validate_patch_promotion"


def contract_errors(source):
    errors = []
    if not re.search(r"(?m)^permissions:\n  contents: read\n", source):
        errors.append("token permission changed")
    if re.search(r"(?m)^\\s+[a-z_-]+:\\s*write\\s*$", source):
        errors.append("write permission requested")
    if any(source.count(marker) != 1 for marker in (PREPARE, GATE, VALIDATE, UPLOAD)):
        return errors + ["missing or duplicate preparation, validation or upload"]
    prepare = source.index(PREPARE)
    gate = source.index(GATE)
    upload = source.index(UPLOAD)
    if not prepare < gate < upload:
        errors.append("artifact validation must precede upload")
    step = source[gate:upload]
    required = (
        "EXPECTED_HEAD: ${{ github.event.pull_request.head.sha || github.sha }}",
        "EXPECTED_RUN_ID: ${{ github.run_id }}",
        "EXPECTED_ATTEMPT: ${{ github.run_attempt }}",
        'test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"',
        "--artifact phase1-patch-evidence",
        "--checkout .",
        '--expected-head "$EXPECTED_HEAD"',
        '--run-id "$EXPECTED_RUN_ID"',
        '--attempt "$EXPECTED_ATTEMPT"',
        "git diff --exit-code -- .",
        "git diff --cached --exit-code -- .",
    )
    for item in required:
        if item not in step:
            errors.append("missing pre-upload guard: " + item)
    return errors


class PreuploadGateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_live_workflow_has_fail_closed_gate(self):
        self.assertEqual([], contract_errors(self.source))

    def test_rejects_missing_validation(self):
        self.assertTrue(contract_errors(self.source.replace(VALIDATE, "echo skipped", 1)))

    def test_rejects_validation_after_upload(self):
        source = self.source
        gate = source.index(GATE)
        upload = source.index(UPLOAD)
        gate_step = source[gate:upload]
        moved = source[:gate] + source[upload:] + "\n" + gate_step
        self.assertTrue(contract_errors(moved))

    def test_rejects_wrong_run_identity(self):
        self.assertTrue(contract_errors(self.source.replace(
            "EXPECTED_RUN_ID: ${{ github.run_id }}",
            "EXPECTED_RUN_ID: 123", 1)))

    def test_rejects_missing_attempt(self):
        self.assertTrue(contract_errors(self.source.replace(
            '--attempt "$EXPECTED_ATTEMPT"', "--attempt 1", 1)))

    def test_rejects_missing_checkout_binding(self):
        self.assertTrue(contract_errors(self.source.replace(
            "--checkout .", "--checkout /tmp", 1)))

    def test_rejects_removed_worktree_check(self):
        self.assertTrue(contract_errors(self.source.replace(
            "git diff --cached --exit-code -- .", "echo skipped", 1)))

    def test_rejects_permission_expansion(self):
        self.assertTrue(contract_errors(self.source.replace(
            "contents: read", "contents: write", 1)))


if __name__ == "__main__":
    unittest.main()
