"""Fail-closed validation of normalized *external* merge evidence.

This module never queries GitHub or performs a merge. The caller must independently
fetch current PR, ruleset, protected-branch and exact-head job records immediately
before merging. Passing fixture tests does not prove live ruleset enforcement,
scheduler-origin execution, or an independently authorized worker.
"""
import re

REQUIRED = frozenset({"unit-tests", "plugin-contract", "deployment-smoke"})
SHA = re.compile(r"[0-9a-f]{40}\Z")


def verify_merge_evidence(pr, ruleset, jobs, *, expected_base, expected_head):
    errors = []
    if not all(isinstance(x, str) and SHA.fullmatch(x)
               for x in (expected_base, expected_head)):
        errors.append("invalid expected commit SHA")
    if not isinstance(pr, dict) or not isinstance(ruleset, dict) or not isinstance(jobs, list):
        return errors + ["missing or malformed external evidence"]

    if pr.get("base_branch") != "main" or pr.get("base_sha") != expected_base:
        errors.append("base changed")
    if pr.get("head_sha") != expected_head:
        errors.append("head changed")
    if pr.get("state") != "open" or pr.get("draft") is not False:
        errors.append("PR not ready")
    if pr.get("mergeable") is not True:
        errors.append("PR not confirmed mergeable")

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
            continue
        if name in seen:
            errors.append("duplicate job")
        seen.add(name)
        if (job.get("head_sha") != expected_head
                or job.get("status") != "completed"
                or job.get("conclusion") != "success"
                or job.get("source") != "GitHub Actions"):
            errors.append(str(name) + ": exact-head CI unverified")
    if seen != REQUIRED:
        errors.append("required CI jobs missing")
    return errors
