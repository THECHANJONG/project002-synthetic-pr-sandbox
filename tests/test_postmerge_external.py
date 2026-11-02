"""Negative controls for external postmerge CI verification; synthetic only."""
import copy
import unittest
from scripts.verify_postmerge_external import verify, UnverifiedPostmerge, REPO

SHA = "a" * 40
RUN_ID = 12345


def sample():
    run = {"id": RUN_ID, "run_attempt": 1,
           "repository": {"full_name": REPO},
           "path": ".github/workflows/synthetic-ci.yml",
           "event": "push", "head_branch": "main", "head_sha": SHA,
           "status": "completed", "conclusion": "success"}
    jobs = [{"name": name, "run_id": RUN_ID, "run_attempt": 1,
             "head_sha": SHA, "status": "completed", "conclusion": "success"}
            for name in ("unit-tests", "plugin-contract", "deployment-smoke")]
    return run, jobs, {"name": "main", "commit": {"sha": SHA}}


class ExternalPostmergeTests(unittest.TestCase):
    def reject(self, change):
        run, jobs, branch = copy.deepcopy(sample())
        change(run, jobs, branch)
        with self.assertRaises(UnverifiedPostmerge):
            verify(run, jobs, branch, run_id=RUN_ID, expected_sha=SHA)

    def test_success_remains_bounded(self):
        result = verify(*sample(), run_id=RUN_ID, expected_sha=SHA)
        self.assertEqual(result["result"], "EXTERNAL_POSTMERGE_MAIN_CI_VERIFIED")
        self.assertEqual(result["scheduler_invocation_attestation"], "UNAVAILABLE")
        self.assertFalse(result["original_private_main_verified"])

    def test_rejects_pr_event(self):
        self.reject(lambda r, j, b: r.update(event="pull_request"))

    def test_rejects_other_repository(self):
        self.reject(lambda r, j, b: r["repository"].update(full_name="other/repo"))

    def test_rejects_wrong_workflow(self):
        self.reject(lambda r, j, b: r.update(path=".github/workflows/other.yml"))

    def test_rejects_stale_main(self):
        self.reject(lambda r, j, b: b["commit"].update(sha="b" * 40))

    def test_rejects_other_attempt(self):
        self.reject(lambda r, j, b: j[0].update(run_attempt=2))

    def test_rejects_bool_run_id(self):
        self.reject(lambda r, j, b: r.update(id=True))

    def test_rejects_duplicate_job(self):
        self.reject(lambda r, j, b: j[1].update(name="unit-tests"))

    def test_rejects_failed_job(self):
        self.reject(lambda r, j, b: j[0].update(conclusion="failure"))

    def test_rejects_missing_job(self):
        self.reject(lambda r, j, b: j.pop())

    def test_rejects_mismatched_head(self):
        self.reject(lambda r, j, b: j[0].update(head_sha="b" * 40))

    def test_rejects_nonfinal_run(self):
        self.reject(lambda r, j, b: r.update(status="in_progress"))

    def test_rejects_unknown_job(self):
        self.reject(lambda r, j, b: j[2].update(name="arbitrary"))


if __name__ == "__main__":
    unittest.main()
