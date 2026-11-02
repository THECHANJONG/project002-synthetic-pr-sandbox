"""Fail-closed validation of normalized *external* merge evidence.

This module never queries GitHub or performs a merge. The caller must independently
fetch current PR, ruleset, protected-branch and exact-head job records immediately
before merging. Passing fixture tests does not prove live ruleset enforcement,
scheduler-origin execution, or an independently authorized worker.
"""
import re

REQUIRED = frozenset({"unit-tests", "plugin-contract", "deployment-smoke"})
SHA = re.compile(r"[0-9a-f]{40}\Z")


def verify_merge_evidence(pr, ruleset, jobs, *, expected_base, expected_head,
                          run=None, expected_repo=None, expected_workflow=None):
    errors = []
    if not all(isinstance(x, str) and SHA.fullmatch(x)
               for x in (expected_base, expected_head)):
        errors.append("invalid expected commit SHA")
    if (type(expected_repo) is not str or "/" not in expected_repo
            or type(expected_workflow) is not str
            or not expected_workflow.startswith(".github/workflows/")
            or not expected_workflow.endswith((".yml", ".yaml"))):
        errors.append("expected repository/workflow identity missing")
    if (type(pr) is not dict or type(ruleset) is not dict
            or type(jobs) is not list or type(run) is not dict):
        return errors + ["missing or malformed external evidence"]

    if pr.get("base_branch") != "main" or pr.get("base_sha") != expected_base:
        errors.append("base changed")
    if pr.get("head_sha") != expected_head:
        errors.append("head changed")
    if (type(pr.get("head_branch")) is not str or not pr["head_branch"]
            or pr["head_branch"] == "main"):
        errors.append("PR source branch not verified")
    if pr.get("state") != "open" or pr.get("draft") is not False:
        errors.append("PR not ready")
    if pr.get("mergeable") is not True:
        errors.append("PR not confirmed mergeable")
    if (type(pr.get("number")) is not int or pr["number"] <= 0
            or pr.get("repository") != expected_repo):
        errors.append("PR number/repository not verified")

    if ruleset.get("enforcement") != "active" or ruleset.get("branch") != "main":
        errors.append("main protection not active")
    if ruleset.get("bypass_actors") != []:
        errors.append("bypass actors not verified empty")
    # A ruleset with no explicit bypass actors is insufficient if the caller
    # still has an effective bypass. Require the server's effective permission.
    if ruleset.get("current_user_can_bypass") != "never":
        errors.append("effective bypass permission not verified absent")
    # The branch endpoint is an independent readback of applied protection.
    if ruleset.get("branch_protected") is not True:
        errors.append("main branch not confirmed protected")
    if ruleset.get("require_pull_request") is not True:
        errors.append("PR rule missing")
    if ruleset.get("require_up_to_date") is not True:
        errors.append("up-to-date rule missing")
    checks = ruleset.get("required_checks")
    if not isinstance(checks, list):
        errors.append("required checks not verified")
    else:
        observed = {}
        for check in checks:
            if not isinstance(check, dict):
                errors.append("invalid check entry")
                continue
            name = check.get("context")
            if not isinstance(name, str):
                errors.append("invalid check context")
                continue
            if name in observed:
                errors.append("duplicate required check")
            observed[name] = check.get("source")
        if set(observed) != REQUIRED or any(observed.get(n) != "GitHub Actions" for n in REQUIRED):
            errors.append("required checks or trusted source mismatch")

    # Prevent combining green jobs from unrelated runs or rerun attempts,
    # even when their exact commit SHA happens to be identical.
    run_id, attempt = run.get("id"), run.get("run_attempt")
    if (type(run_id) is not int or run_id <= 0
            or type(attempt) is not int or attempt <= 0
            or run.get("head_sha") != expected_head
            or run.get("repository") != expected_repo
            or run.get("workflow_path") != expected_workflow
            or run.get("head_branch") != pr.get("head_branch")
            or run.get("pr_number") != pr.get("number")
            or type(run.get("pr_number")) is not int
            or run.get("event") != "pull_request"
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"):
        errors.append("PR workflow run identity/success unverified")
    # The complete CI job inventory must be checked, not just a green subset.
    # An extra failed security job must never be silently ignored.
    if len(jobs) != len(REQUIRED):
        errors.append("unexpected CI job count")
    seen = set()
    for job in jobs:
        if not isinstance(job, dict):
            errors.append("malformed job")
            continue
        name = job.get("name")
        if not isinstance(name, str):
            errors.append("invalid job name")
            continue
        if name not in REQUIRED:
            errors.append("unexpected CI job")
            continue
        if name in seen:
            errors.append("duplicate job")
        seen.add(name)
        if (job.get("head_sha") != expected_head
                or job.get("status") != "completed"
                or job.get("conclusion") != "success"
                or job.get("source") != "GitHub Actions"):
            errors.append(str(name) + ": exact-head CI unverified")
        if (type(job.get("run_id")) is not int
                or type(job.get("run_attempt")) is not int
                or job["run_id"] != run_id
                or job["run_attempt"] != attempt):
            errors.append(str(name) + ": mixed workflow run or attempt")
    if seen != REQUIRED:
        errors.append("required CI jobs missing")
    return errors
