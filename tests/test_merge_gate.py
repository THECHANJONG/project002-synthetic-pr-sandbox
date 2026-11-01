"""Pure negative controls; these are NOT live GitHub protection tests."""
import copy
import unittest
from scripts.merge_gate import verify_merge_evidence

BASE = "a" * 40
HEAD = "b" * 40
REPO = "THECHANJONG/project002-synthetic-pr-sandbox"
WORKFLOW = ".github/workflows/synthetic-ci.yml"
RUN = dict(id=123, run_attempt=2, head_sha=HEAD, repository=REPO,
           workflow_path=WORKFLOW, pr_number=42, event="pull_request",
           status="completed", conclusion="success")
NAMES = ("unit-tests", "plugin-contract", "deployment-smoke")


def evidence():
    pr = dict(number=42, repository=REPO, base_branch="main", base_sha=BASE, head_sha=HEAD,
              state="open", draft=False, mergeable=True)
    rules = dict(enforcement="active", branch="main", bypass_actors=[],
                 current_user_can_bypass="never", branch_protected=True,
                 require_pull_request=True, require_up_to_date=True,
                 required_checks=[dict(context=n, source="GitHub Actions") for n in NAMES])
    jobs = [dict(name=n, head_sha=HEAD, status="completed",
                 conclusion="success", source="GitHub Actions",
                 run_id=123, run_attempt=2) for n in NAMES]
    return pr, rules, jobs


class MergeGateTests(unittest.TestCase):
    def check_rejected(self, mutate):
        data = list(copy.deepcopy(evidence()))
        mutate(data)
        self.assertTrue(verify_merge_evidence(*data, expected_base=BASE, expected_head=HEAD,
                            run=RUN, expected_repo=REPO, expected_workflow=WORKFLOW))

    def test_complete_normalized_evidence(self):
        self.assertEqual([], verify_merge_evidence(*evidence(), expected_base=BASE, expected_head=HEAD,
                            run=RUN, expected_repo=REPO, expected_workflow=WORKFLOW))

    def test_stale_head(self):
        self.check_rejected(lambda d: d[0].update(head_sha="c" * 40))

    def test_changed_base(self):
        self.check_rejected(lambda d: d[0].update(base_sha="c" * 40))

    def test_draft(self):
        self.check_rejected(lambda d: d[0].update(draft=True))

    def test_mergeable_unknown(self):
        self.check_rejected(lambda d: d[0].update(mergeable=None))

    def test_inactive_protection(self):
        self.check_rejected(lambda d: d[1].update(enforcement="disabled"))

    def test_bypass_actor(self):
        self.check_rejected(lambda d: d[1].update(bypass_actors=["admin"]))

    def test_missing_pr_rule(self):
        self.check_rejected(lambda d: d[1].update(require_pull_request=False))

    def test_missing_freshness(self):
        self.check_rejected(lambda d: d[1].update(require_up_to_date=False))

    def test_spoofed_check_source(self):
        self.check_rejected(lambda d: d[1]["required_checks"][0].update(source="unknown"))

    def test_missing_job(self):
        self.check_rejected(lambda d: d[2].pop())

    def test_duplicate_job(self):
        self.check_rejected(lambda d: d[2].append(copy.deepcopy(d[2][0])))

    def test_job_failed(self):
        self.check_rejected(lambda d: d[2][0].update(conclusion="failure"))

    def test_job_on_other_head(self):
        self.check_rejected(lambda d: d[2][0].update(head_sha="c" * 40))

    def test_untrusted_job(self):
        self.check_rejected(lambda d: d[2][0].update(source="other"))

    def test_malformed_external_payload(self):
        self.assertTrue(verify_merge_evidence(None, None, None, expected_base=BASE, expected_head=HEAD,
                            run=RUN, expected_repo=REPO, expected_workflow=WORKFLOW))

    def test_unhashable_check_context(self):
        self.check_rejected(lambda d: d[1]["required_checks"][0].update(context=["bad"]))

    def test_unhashable_job_name(self):
        self.check_rejected(lambda d: d[2][0].update(name=["bad"]))

    def test_invalid_expected_sha(self):
        self.assertTrue(verify_merge_evidence(*evidence(), expected_base="not-sha", expected_head=HEAD,
                            run=RUN, expected_repo=REPO, expected_workflow=WORKFLOW))


    def test_mixed_run_id_same_sha_rejected(self):
        self.check_rejected(lambda d: d[2][0].update(run_id=124))

    def test_mixed_attempt_same_sha_rejected(self):
        self.check_rejected(lambda d: d[2][1].update(run_attempt=1))

    def test_bool_run_id_rejected(self):
        self.check_rejected(lambda d: d[2][2].update(run_id=True))

    def test_missing_run_rejected(self):
        self.assertTrue(verify_merge_evidence(*evidence(), expected_base=BASE,
                        expected_head=HEAD, expected_repo=REPO,
                        expected_workflow=WORKFLOW))

    def test_wrong_workflow_rejected(self):
        self.assertTrue(verify_merge_evidence(*evidence(), expected_base=BASE,
                        expected_head=HEAD, run={**RUN, "workflow_path": "other.yml"},
                        expected_repo=REPO, expected_workflow=WORKFLOW))

    def test_wrong_pr_binding_rejected(self):
        self.assertTrue(verify_merge_evidence(*evidence(), expected_base=BASE,
                        expected_head=HEAD, run={**RUN, "pr_number": 41},
                        expected_repo=REPO, expected_workflow=WORKFLOW))

    def test_wrong_run_attempt_type_rejected(self):
        self.assertTrue(verify_merge_evidence(*evidence(), expected_base=BASE,
                        expected_head=HEAD, run={**RUN, "run_attempt": True},
                        expected_repo=REPO, expected_workflow=WORKFLOW))

    def test_non_pr_run_rejected(self):
        self.assertTrue(verify_merge_evidence(*evidence(), expected_base=BASE,
                        expected_head=HEAD, run={**RUN, "event": "push"},
                        expected_repo=REPO, expected_workflow=WORKFLOW))

    def test_wrong_run_repository_rejected(self):
        self.assertTrue(verify_merge_evidence(*evidence(), expected_base=BASE,
                        expected_head=HEAD, run={**RUN, "repository": "other/repo"},
                        expected_repo=REPO, expected_workflow=WORKFLOW))

if __name__ == "__main__":
    unittest.main()
