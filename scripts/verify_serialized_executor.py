"""Fail-closed, read-only identity preflight for a serialized GitHub Actions probe.

This is NOT a distributed lock, durable queue, scheduler attestation or permission
to mutate an external ledger. A GitHub concurrency group may replace a pending run.
"""
import json
import os
import re
import sys

SHA = re.compile(r"[0-9a-f]{40}\Z")
POSITIVE = re.compile(r"[1-9][0-9]{0,19}\Z")
REPO = "THECHANJONG/project002-synthetic-pr-sandbox"
WORKFLOW = "phase1-serialized-executor-readonly"


class InvalidExecutorIdentity(ValueError):
    pass


def verify_identity(env):
    if type(env) is not dict:
        raise InvalidExecutorIdentity("environment must be an object")
    if env.get("GITHUB_REPOSITORY") != REPO:
        raise InvalidExecutorIdentity("wrong repository")
    if env.get("GITHUB_WORKFLOW") != WORKFLOW:
        raise InvalidExecutorIdentity("wrong workflow")
    if env.get("GITHUB_EVENT_NAME") not in ("push", "pull_request"):
        raise InvalidExecutorIdentity("unexpected trigger")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        value = env.get(key)
        if type(value) is not str or not POSITIVE.fullmatch(value):
            raise InvalidExecutorIdentity("invalid " + key)
    expected = env.get("EXPECTED_HEAD")
    actual = env.get("CHECKED_OUT_HEAD")
    if (type(expected) is not str or not SHA.fullmatch(expected)
            or type(actual) is not str or not SHA.fullmatch(actual)
            or expected != actual):
        raise InvalidExecutorIdentity("exact HEAD mismatch")
    return {
        "status": "READ_ONLY_IDENTITY_PREFLIGHT_VERIFIED",
        "exact_head": expected,
        "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": env["GITHUB_RUN_ATTEMPT"],
        "execution_scope": "SINGLE_GITHUB_ACTIONS_WORKFLOW_GROUP",
        "github_concurrency_is_durable_queue": False,
        "shared_remote_cas_lease_fencing": "NOT_PROVEN",
        "scheduler_invocation_attestation": "UNAVAILABLE",
        "mutable_authority": "NOT_GRANTED",
    }


def main():
    try:
        result = verify_identity(dict(os.environ))
    except InvalidExecutorIdentity as exc:
        print("SERIALIZED_EXECUTOR_REJECTED: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
