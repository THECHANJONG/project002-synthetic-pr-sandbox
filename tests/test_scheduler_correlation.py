"""Synthetic controls for scheduler/GitHub correlation; not live E2E."""
import copy
import unittest
from scripts.verify_scheduler_correlation import correlate, InvalidCorrelation

ID = "adf6de8c-da00-8327-9cf9-8994b203c8ab"
HEAD = "a" * 40
MERGE = "b" * 40
NAMES = ("unit-tests", "plugin-contract", "deployment-smoke")


def run(run_id, sha, event, branch, completed_at, pr_number=None):
    obj = dict(id=run_id, run_attempt=1, head_sha=sha, event=event,
               head_branch=branch, status="completed", conclusion="success",
               completed_at=completed_at,
               jobs=[dict(name=name, status="completed", conclusion="success",
                          head_sha=sha, run_id=run_id, run_attempt=1)
                     for name in NAMES])
    if pr_number is not None:
        obj["pr_number"] = pr_number
    return obj


def evidence():
    platform = dict(id=ID, recorded_status="completed",
                    scheduled_for="2026-11-01T22:00:00Z",
                    started_at="2026-11-01T22:02:00Z",
                    completed_at="2026-11-01T22:12:00Z")
    github = dict(automation_run_id=ID,
                  pr=dict(number=15, head_sha=HEAD, merge_commit_sha=MERGE,
                          merged=True, base_branch="main",
                          head_branch="test/correlation",
                          created_at="2026-11-01T22:03:00Z",
                          merged_at="2026-11-01T22:07:00Z"),
                  pr_ci=run(123, HEAD, "pull_request", "test/correlation",
                            "2026-11-01T22:06:00Z", 15),
                  postmerge_ci=run(124, MERGE, "push", "main",
                                   "2026-11-01T22:09:00Z"),
                  main_readback_sha=MERGE)
    return platform, github


class CorrelationTests(unittest.TestCase):
    def reject(self, change):
        p, g = copy.deepcopy(evidence())
        change(p, g)
        with self.assertRaises(InvalidCorrelation):
            correlate(p, g)

    def test_complete_evidence_is_still_not_attestation(self):
        result = correlate(*evidence())
        self.assertEqual(result["correlation"], "CORRELATED_NOT_ATTESTED")
        self.assertEqual(result["autonomous_development_e2e"], "NOT_PROVEN")

    def test_missing_platform_completion(self):
        self.reject(lambda p, g: p.update(recorded_status="in_progress"))

    def test_forged_run_id_binding(self):
        self.reject(lambda p, g: g.update(automation_run_id="other"))

    def test_bool_pr_number(self):
        self.reject(lambda p, g: g["pr"].update(number=True))

    def test_wrong_pr_ci_branch(self):
        self.reject(lambda p, g: g["pr_ci"].update(head_branch="main"))

    def test_wrong_postmerge_sha(self):
        self.reject(lambda p, g: g["postmerge_ci"].update(head_sha=HEAD))

    def test_mixed_ci_run_id(self):
        self.reject(lambda p, g: g["pr_ci"]["jobs"][0].update(run_id=999))

    def test_duplicate_ci_job(self):
        self.reject(lambda p, g: g["postmerge_ci"]["jobs"][1].update(name="unit-tests"))

    def test_unverified_main(self):
        self.reject(lambda p, g: g.update(main_readback_sha=HEAD))

    def test_pr_created_before_scheduler(self):
        self.reject(lambda p, g: g["pr"].update(created_at="2026-11-01T21:59:00Z"))

    def test_postmerge_ci_after_platform_completion(self):
        self.reject(lambda p, g: g["postmerge_ci"].update(completed_at="2026-11-01T22:13:00Z"))

    def test_malformed_timestamp(self):
        self.reject(lambda p, g: p.update(started_at="not-a-time"))

    def test_missing_pr(self):
        self.reject(lambda p, g: g.update(pr=None))

    def test_bool_ci_run_id(self):
        self.reject(lambda p, g: g["pr_ci"].update(id=True))


if __name__ == "__main__":
    unittest.main()
