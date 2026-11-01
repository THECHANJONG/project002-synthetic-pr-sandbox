"""Fail-closed evidence for cross-host *non*-atomic artifact-name creation.

A live negative control found that upload-artifact v4 allows TWO artifacts
with the SAME name in one workflow run. Never use artifact names as a CAS,
lock, lease or fencing authority. This verifier checks both returned artifact IDs and one downloaded receipt and explicitly reports the non-CAS boundary.
"""
import json
import os
import re
import sys
from pathlib import Path

from scripts.verify_runner_evidence import InvalidRunnerEvidence, verify_two_hosts

SHA = re.compile(r"[0-9a-f]{40}\Z")
ID = re.compile(r"[1-9][0-9]{0,19}\Z")


class InvalidArtifactClaim(ValueError):
    pass


def verify_claim(a, b, artifacts, expected_head, run_id):
    if type(expected_head) is not str or not SHA.fullmatch(expected_head):
        raise InvalidArtifactClaim("invalid expected head")
    if type(run_id) is not str or not ID.fullmatch(run_id):
        raise InvalidArtifactClaim("invalid run ID")
    for label, worker in (("host-a", a), ("host-b", b)):
        if type(worker) is not dict or worker.get("worker") != label:
            raise InvalidArtifactClaim("wrong worker identity")
        if worker.get("claim_outcome") != "success":
            raise InvalidArtifactClaim("both independent uploads must succeed for counterexample")
        if type(worker.get("artifact_id")) is not str or not ID.fullmatch(worker["artifact_id"]):
            raise InvalidArtifactClaim("missing artifact ID")
    if a["artifact_id"] == b["artifact_id"]:
        raise InvalidArtifactClaim("artifact IDs not distinct")
    try:
        distinct = verify_two_hosts(a, b, expected_head)
    except InvalidRunnerEvidence as exc:
        raise InvalidArtifactClaim(str(exc)) from exc
    if type(artifacts) is not dict or set(artifacts) != {
        "schema_version", "project_id", "claim_type", "worker",
        "head_sha", "boot_id", "run_id"
    }:
        raise InvalidArtifactClaim("invalid downloaded artifact schema")
    if type(artifacts["schema_version"]) is not int or artifacts["schema_version"] != 1:
        raise InvalidArtifactClaim("invalid artifact schema version")
    matches = [w for w in (a, b) if artifacts["worker"] == w["worker"]
               and artifacts["boot_id"] == w["boot_id"]]
    if (len(matches) != 1 or artifacts["project_id"] != "PROJECT_002_SYNTHETIC"
            or artifacts["claim_type"] != "IMMUTABLE_SINGLE_CREATE"
            or artifacts["head_sha"] != expected_head or artifacts["run_id"] != run_id):
        raise InvalidArtifactClaim("downloaded artifact not bound to either verified host")
    return {
        "result": "TWO_SAME_NAME_UPLOADS_ONE_ARTIFACT_READ_BACK",
        "exact_head": expected_head,
        "run_id": run_id,
        "artifact_ids": [a["artifact_id"], b["artifact_id"]],
        "distinct_boot_ids": distinct["boot_ids"],
        "same_name_claim_in_workflow": "BOTH_SUCCEEDED",
        "downloaded_worker": artifacts["worker"],
        "second_artifact_readback": "NOT_VERIFIED_IN_WORKFLOW",
        "github_artifact_inventory_crosscheck": "REQUIRED_FOR_DUPLICATE_NAME_CLAIM",
        "artifact_name_is_safe_lock": False,
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
                for key in ("head_sha", "hostname", "boot_id", "claim_outcome", "artifact_id")}}
        a = record("HOST_A_", "host-a")
        b = record("HOST_B_", "host-b")
        artifacts = json.loads(Path("claim.json").read_text(encoding="utf-8"))
        result = verify_claim(a, b, artifacts, os.environ["EXPECTED_HEAD"], os.environ["EXPECTED_RUN_ID"])
    except (InvalidArtifactClaim, KeyError, OSError, ValueError, UnicodeError) as exc:
        print("ARTIFACT_COUNTEREXAMPLE_REJECTED: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
