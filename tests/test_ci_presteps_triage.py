"""Regression tests for read-only CI failure triage using synthetic metadata."""
import copy
import unittest

from scripts.triage_ci_presteps import InvalidEvidence, triage

SHA = "a" * 40
NAMES = ("unit-tests", "plugin-contract", "deployment-smoke")


def fixture(conclusion="failure", steps=None):
    run = {"id": 123, "run_attempt": 1, "head_sha": SHA, "event": "push",
           "status": "completed", "conclusion": conclusion}
    jobs = [{"id": i + 10, "name": n, "conclusion": conclusion, "steps": steps,
             "run_id": 123, "run_attempt": 1, "head_sha": SHA,
             "runner_id": 0 if conclusion == "failure" else i + 1,
             "runner_name": "" if conclusion == "failure" else "GitHub Actions " + str(i + 1)}
            for i, n in enumerate(NAMES)]
    checks = [{"id": i + 10, "name": n, "conclusion": conclusion,
               "output": {"annotations_count": 2}} for i, n in enumerate(NAMES)]
    return run, jobs, checks


class TriageTests(unittest.TestCase):
    def test_failed_without_steps_is_suspicion_not_root_cause(self):
        result = triage(*fixture())
        self.assertEqual(result["classification"], "ALL_JOBS_FAILED_NO_STEPS_RUNNER_ID_ZERO")
        self.assertEqual(result["runner_assignment_metadata"], "ALL_ZERO_ID_EMPTY_NAME")
        self.assertEqual(result["runner_not_assigned"], "NOT_PROVEN")
        self.assertEqual(result["root_cause"], "NOT_PROVEN")
        self.assertEqual(result["runner_or_billing_failure"], "NOT_PROVEN")
        self.assertEqual(result["annotation_counts"]["unit-tests"], 2)
        self.assertFalse(result["safe_to_merge"])

    def test_success_requires_steps(self):
        result = triage(*fixture("success", [{"name": "Set up job"}]))
        self.assertEqual(result["classification"], "EXACT_RUN_JOBS_SUCCESS_STEPS_PRESENT")
        self.assertEqual(result["runner_assignment_metadata"], "ALL_POSITIVE_ID_NAMED")
        self.assertFalse(result["safe_to_merge"])

    def test_success_without_steps_is_inconclusive(self):
        self.assertEqual(triage(*fixture("success"))["classification"], "INCONCLUSIVE_FAIL_CLOSED")

    def test_mixed_results_fail_closed(self):
        run, jobs, checks = fixture()
        jobs[0]["conclusion"] = "success"
        checks[0]["conclusion"] = "success"
        self.assertEqual(triage(run, jobs, checks)["classification"], "INCONCLUSIVE_FAIL_CLOSED")

    def test_rejects_missing_job(self):
        run, jobs, checks = fixture()
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs[:-1], checks)

    def test_rejects_duplicate_job(self):
        run, jobs, checks = fixture()
        jobs[1]["name"] = jobs[0]["name"]
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_rejects_check_job_mismatch(self):
        run, jobs, checks = fixture()
        checks[0]["conclusion"] = "success"
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_rejects_bool_annotation_count(self):
        run, jobs, checks = fixture()
        checks[0]["output"]["annotations_count"] = True
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_rejects_type_coerced_job_id(self):
        run, jobs, checks = fixture()
        jobs[0]["id"] = True
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_rejects_bad_sha(self):
        run, jobs, checks = fixture()
        run["head_sha"] = "not-a-sha"
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_rejects_incomplete_run(self):
        run, jobs, checks = fixture()
        run["status"] = "queued"
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_rejects_unexpected_job(self):
        run, jobs, checks = fixture()
        jobs[2]["name"] = "another-job"
        checks[2]["name"] = "another-job"
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_mixed_run_ids_rejected(self):
        run, jobs, checks = fixture()
        jobs[0]["run_id"] = 124
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_mixed_attempt_rejected(self):
        run, jobs, checks = fixture()
        jobs[1]["run_attempt"] = 2
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_job_wrong_head_rejected(self):
        run, jobs, checks = fixture()
        jobs[2]["head_sha"] = "b" * 40
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_bool_run_id_rejected(self):
        run, jobs, checks = fixture()
        run["id"] = True
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_bool_runner_id_rejected(self):
        run, jobs, checks = fixture()
        jobs[0]["runner_id"] = False
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_contradictory_runner_name_rejected(self):
        run, jobs, checks = fixture()
        jobs[0]["runner_name"] = "GitHub Actions 999"
        with self.assertRaises(InvalidEvidence):
            triage(run, jobs, checks)

    def test_mixed_runner_metadata_does_not_prove_unassigned(self):
        run, jobs, checks = fixture()
        jobs[0]["runner_id"] = 100
        jobs[0]["runner_name"] = "GitHub Actions 100"
        result = triage(run, jobs, checks)
        self.assertEqual(result["classification"], "ALL_JOBS_FAILED_NO_STEPS_OBSERVED")
        self.assertEqual(result["runner_assignment_metadata"], "MIXED_RUNNER_METADATA")
        self.assertEqual(result["runner_not_assigned"], "NOT_PROVEN")

    def test_runner_zero_not_root_cause(self):
        result = triage(*fixture())
        self.assertEqual(result["root_cause"], "NOT_PROVEN")
        self.assertEqual(result["runner_or_billing_failure"], "NOT_PROVEN")
        self.assertFalse(result["safe_to_merge"])


if __name__ == "__main__":
    unittest.main()
