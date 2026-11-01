"""Regression guards for the isolated synthetic GitHub Actions workflow.

These tests validate configuration, not a live scheduler, branch protection,
or production deployment. Negative controls deliberately mutate the fixture.
"""
import re
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/synthetic-ci.yml"
CHECKOUT = "uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
EVENT_HEAD = "${{ github.event.pull_request.head.sha || github.sha }}"
ASSERT_HEAD = 'test "$(git rev-parse HEAD)" = "$EXPECTED_HEAD"'
REQUIRED_JOBS = {"unit-tests", "plugin-contract", "deployment-smoke"}


def validate_workflow(source):
    problems = []
    if not re.search(r"(?m)^permissions:\n  contents: read\n", source):
        problems.append("missing read-only token permission")
    if re.search(r"(?m)^\s+[a-z_-]+:\s*write\s*$", source):
        problems.append("write permission")
    if not all(line in source for line in (
        "concurrency:",
        "  group: synthetic-ci-\u0024{{ github.workflow }}-\u0024{{ github.event.pull_request.number || github.ref }}",
        "  cancel-in-progress: true",
    )):
        problems.append("missing bounded concurrency")
    if "secrets." in source:
        problems.append("secret reference")
    if not re.search(r"(?m)^  pull_request:\s*$", source):
        problems.append("missing PR trigger")

    blocks = dict(re.findall(
        r"(?ms)^  ([a-z][a-z0-9-]*):\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)",
        source.split("\njobs:\n", 1)[-1]
    ))
    if set(blocks) != REQUIRED_JOBS:
        problems.append("unexpected or missing jobs")

    for name in REQUIRED_JOBS:
        body = blocks.get(name, "")
        if "    timeout-minutes: 10\n" not in body:
            problems.append(name + ": missing job timeout")
        for label, expected in (
            ("pinned checkout", CHECKOUT),
            ("exact checkout ref", "ref: " + EVENT_HEAD),
            ("nonpersistent credentials", "persist-credentials: false"),
            ("expected head environment", "EXPECTED_HEAD: " + EVENT_HEAD),
            ("runtime HEAD assertion", ASSERT_HEAD),
        ):
            if expected not in body:
                problems.append(name + ": missing " + label)
    return problems


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid = WORKFLOW.read_text(encoding="utf-8")

    def test_live_file_matches_synthetic_contract(self):
        self.assertEqual([], validate_workflow(self.valid))

    def test_rejects_implicit_merge_ref(self):
        changed = self.valid.replace("ref: " + EVENT_HEAD, "ref: ${{ github.sha }}", 1)
        self.assertTrue(validate_workflow(changed))

    def test_rejects_missing_runtime_assertion(self):
        changed = self.valid.replace(ASSERT_HEAD, "echo skipped", 1)
        self.assertTrue(validate_workflow(changed))

    def test_rejects_persistent_credentials(self):
        changed = self.valid.replace("persist-credentials: false", "persist-credentials: true", 1)
        self.assertTrue(validate_workflow(changed))

    def test_rejects_write_permissions(self):
        changed = self.valid.replace("contents: read", "contents: write", 1)
        self.assertTrue(validate_workflow(changed))

    def test_rejects_unpinned_checkout(self):
        changed = self.valid.replace(CHECKOUT, "uses: actions/checkout@v4", 1)
        self.assertTrue(validate_workflow(changed))

    def test_rejects_removed_job(self):
        changed = self.valid.replace("  deployment-smoke:\n", "  missing-job:\n", 1)
        self.assertTrue(validate_workflow(changed))

    def test_rejects_unbounded_concurrency(self):
        changed = self.valid.replace("  cancel-in-progress: true", "  cancel-in-progress: false", 1)
        self.assertTrue(validate_workflow(changed))

    def test_rejects_missing_job_timeout(self):
        changed = self.valid.replace("    timeout-minutes: 10", "    timeout-minutes: 0", 1)
        self.assertTrue(validate_workflow(changed))

    def test_rejects_secret_reference(self):
        changed = self.valid + "\n# ${{ secrets.SOME_TOKEN }}\n"
        self.assertTrue(validate_workflow(changed))


if __name__ == "__main__":
    unittest.main()
