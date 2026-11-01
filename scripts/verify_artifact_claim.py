"""Validate one-winner immutable artifact claim across two distinct Actions hosts.

The upload-artifact v4 namespace is an immutable, per-workflow-run artifact store.
This proves bounded single-create contention and cross-host readback only;
it does NOT prove mutable GitHub Contents CAS, lease/fencing or AI cold start.
"""
import json
import os
import re
import sys
from pathlib import Path

from scripts.verify_runner_evidence import InvalidRunnerEvidence, verify_two_hosts

SHA = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")


class InvalidArtifactClaim(ValueError):
    pass


def verify_claim(a, b, artifact, expected_head, run_id):
    if type(expected_head) is not str or not SHA.fullmatch(expected_head):
        raise InvalidArtifactClaim("invalid expected head")
    if type(run_id) is not str or not RUN_ID.fullmatch(run_id):
        raise InvalidArtifactClaim("invalid workflow run ID")
    for label, worker in (("host-a", a), ("host-b", b)):
        if type(worker) is not dict or worker.get("worker") != label:
            raise InvalidArtifactClaim("wrong or missing worker identity")
        if worker.get("claim_outcome") not in ("success", "failure"):
            raise InvalidArtifactClaim("unknown artifact claim outcome")
    try:
        distinct = verify_two_hosts(a, b, expected_head)
    except InvalidRunnerEvidence as exc:
        raise InvalidArtifactClaim(str(exc)) from exc
    winners = [w for w in (a, b) if w["claim_outcome"] == "success"]
    if len(winners) != 1:
        raise InvalidArtifactClaim("exactly one artifact create must succeed")
    winner = winners[0]
    if type(artifact) is not dict or set(artifact) != {
        "schema_version", "project_id", "claim_type", "worker", "head_sha", "boot_id", "run_id"
    }:
        raise InvalidArtifactClaim("unexpected artifact payload schema")
    if type(artifact["schema_version"]) is not int or artifact["schema_version"] != 1:
        raise InvalidArtifactClaim("invalid artifact version")
    if artifact["project_id"] != "PROJECT_002_SYNTHETIC":
        raise InvalidArtifactClaim("not a synthetic artifact")
    if artifact["claim_type"] != "IMMUTABLE_SINGLE_CREATE":
        raise InvalidArtifactClaim("unexpected claim type")
    if (artifact["worker"] != winner["worker"]
            or artifact["head_sha"] != expected_head
            or artifact["boot_id"] != winner["boot_id"]
            or artifact["run_id"] != run_id):
        raise InvalidArtifactClaim("artifact does not match the winning host and run")
    return {
        "result": "TWO_HOST_IMMUTABLE_ARTIFACT_SINGLE_CREATOR_VERIFIED",
        "exact_head": expected_head,
        "run_id": run_id,
        "winning_worker": winner["worker"],
        "distinct_boot_ids": distinct["boot_ids"],
        "immutable_artifact_readback": "VERIFIED",
        "loser_failure_reason": "REQUIRES_INDEPENDENT_LOG_REVIEW",
        "mutable_shared_cas": "NOT_PROVEN",
        "lease_fencing": "NOT_PROVEN",
        "crash_recovery": "NOT_PROVEN",
        "independent_ai_cold_start": "NOT_PROVEN",
        "scheduler_invocation_attestation": "UNAVAILABLE",
    }


def main():
    try:
        def record(prefix, worker):
            return {"worker": worker, **{key: os.environ[prefix + key.upper()]
                for key in ("head_sha", "hostname", "boot_id", "claim_outcome")}}
        a = record("HOST_A_", "host-a")
        b = record("HOST_B_", "host-b")
        payload = json.loads(Path("claim.json").read_text(encoding="utf-8"))
        result = verify_claim(a, b, payload, os.environ["EXPECTED_HEAD"], os.environ["EXPECTED_RUN_ID"])
    except (InvalidArtifactClaim, KeyError, OSError, ValueError, UnicodeError) as exc:
        print("ARTIFACT_CLAIM_REJECTED: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
