"""Live-protection normalization contract; a failing red test is intentional until
the gate rejects unverified server-side branch protection and bypass permission.
This is a pure regression test, NOT proof of live GitHub enforcement by itself.
"""
import unittest
from scripts.merge_gate import verify_merge_evidence

BASE = "a" * 40
HEAD = "b" * 40
REPO = "THECHANJONG/project002-synthetic-pr-sandbox"
WORKFLOW = ".github/workflows/synthetic-ci.yml"
RUN = dict(id=123, run_attempt=1, head_sha=HEAD, repository=REPO,
           workflow_path=WORKFLOW, head_branch="fix/synthetic-test", pr_number=42, event="pull_request",
           status="completed", conclusion="success")
NAMES = ("unit-tests", "plugin-contract", "deployment-smoke")


def evidence():
    pr = dict(number=42, repository=REPO, base_branch="main", head_branch="fix/synthetic-test", base_sha=BASE, head_sha=HEAD,
              state="open", draft=False, mergeable=True)
    rules = dict(enforcement="active", branch="main", bypass_actors=[],
                 current_user_can_bypass="never", branch_protected=True,
                 require_pull_request=True, require_up_to_date=True,
                 required_checks=[dict(context=n, source="GitHub Actions") for n in NAMES])
    jobs = [dict(name=n, head_sha=HEAD, status="completed",
                 conclusion="success", source="GitHub Actions",
                 run_id=123, run_attempt=1) for n in NAMES]
    return pr, rules, jobs


class LiveProtectionContractTests(unittest.TestCase):
    def test_complete_server_readback(self):
        self.assertEqual([], verify_merge_evidence(*evidence(), expected_base=BASE, expected_head=HEAD,
                          run=RUN, expected_repo=REPO, expected_workflow=WORKFLOW))

    def test_rejects_user_with_bypass_permission(self):
        pr, rules, jobs = evidence()
        rules["current_user_can_bypass"] = "always"
        self.assertTrue(verify_merge_evidence(pr, rules, jobs, expected_base=BASE, expected_head=HEAD,
                          run=RUN, expected_repo=REPO, expected_workflow=WORKFLOW))

    def test_rejects_unprotected_branch(self):
        pr, rules, jobs = evidence()
        rules["branch_protected"] = False
        self.assertTrue(verify_merge_evidence(pr, rules, jobs, expected_base=BASE, expected_head=HEAD,
                          run=RUN, expected_repo=REPO, expected_workflow=WORKFLOW))


if __name__ == "__main__":
    unittest.main()
