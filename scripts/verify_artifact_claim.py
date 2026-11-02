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
from urllib.request import Request, urlopen

from scripts.verify_runner_evidence import InvalidRunnerEvidence, verify_two_hosts

SHA = re.compile(r"[0-9a-f]{40}\Z")
ID = re.compile(r"[1-9][0-9]{0,19}\Z")
REPO = "THECHANJONG/project002-synthetic-pr-sandbox"
ARTIFACT_NAME = "phase1-synthetic-single-create"


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



def verify_inventory(a, b, inventory, expected_head, run_id):
    """Independently verify BOTH same-name artifacts via GitHub run inventory.

    This is metadata evidence only, NOT a compare-and-swap, shared lease,
    artifact-content readback, or cross-service transaction.
    """
    if (type(inventory) is not dict or type(inventory.get("total_count")) is not int
            or inventory["total_count"] != 2 or type(inventory.get("artifacts")) is not list
            or len(inventory["artifacts"]) != 2):
        raise InvalidArtifactClaim("artifact inventory incomplete or ambiguous")
    if type(run_id) is not str or not ID.fullmatch(run_id):
        raise InvalidArtifactClaim("invalid inventory run ID")
    if type(expected_head) is not str or not SHA.fullmatch(expected_head):
        raise InvalidArtifactClaim("invalid inventory head")
    ids = set()
    repository_ids = set()
    head_branches = set()
    for artifact in inventory["artifacts"]:
        if type(artifact) is not dict:
            raise InvalidArtifactClaim("malformed artifact record")
        artifact_id = artifact.get("id")
        if (type(artifact_id) is not int or artifact_id <= 0
                or artifact_id in ids or artifact.get("name") != ARTIFACT_NAME
                or artifact.get("expired") is not False):
            raise InvalidArtifactClaim("wrong, duplicate or expired artifact")
        ids.add(artifact_id)
        origin = artifact.get("workflow_run")
        if type(origin) is not dict:
            raise InvalidArtifactClaim("missing artifact run origin")
        repo_id = origin.get("repository_id")
        if (type(origin.get("id")) is not int or origin["id"] != int(run_id)
                or origin.get("head_sha") != expected_head
                or type(origin.get("head_branch")) is not str
                or not origin["head_branch"]
                or type(repo_id) is not int or repo_id <= 0
                or type(origin.get("head_repository_id")) is not int
                or origin["head_repository_id"] != repo_id):
            raise InvalidArtifactClaim("artifact bound to different run, head or repository")
        repository_ids.add(repo_id)
        head_branches.add(origin["head_branch"])
    if (len(repository_ids) != 1 or len(head_branches) != 1
            or ids != {int(a["artifact_id"]), int(b["artifact_id"])}):
        raise InvalidArtifactClaim("artifact inventory differs from independent host outputs")
    return {
        "github_artifact_inventory_crosscheck": "VERIFIED",
        "second_artifact_readback": "METADATA_ONLY_VERIFIED",
        "inventory_artifact_ids": sorted(ids),
        "artifact_name_is_safe_lock": False,
        "shared_durable_cas": "NOT_PROVEN",
    }


def fetch_inventory(run_id):
    """Read public synthetic repository metadata without new token permissions."""
    url = ("https://api.github.com/repos/" + REPO + "/actions/runs/"
           + run_id + "/artifacts?per_page=100")
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "project002-synthetic-artifact-inventory",
    })
    with urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise InvalidArtifactClaim("GitHub inventory request unsuccessful")
        return json.load(response)


def main():
    try:
        def record(prefix, worker):
            return {"worker": worker, **{key: os.environ[prefix + key.upper()]
                for key in ("head_sha", "hostname", "boot_id", "claim_outcome", "artifact_id")}}
        a = record("HOST_A_", "host-a")
        b = record("HOST_B_", "host-b")
        artifacts = json.loads(Path("claim.json").read_text(encoding="utf-8"))
        expected_head = os.environ["EXPECTED_HEAD"]
        run_id = os.environ["EXPECTED_RUN_ID"]
        result = verify_claim(a, b, artifacts, expected_head, run_id)
        inventory = fetch_inventory(run_id)
        result.update(verify_inventory(a, b, inventory, expected_head, run_id))
    except (InvalidArtifactClaim, KeyError, OSError, ValueError, UnicodeError) as exc:
        print("ARTIFACT_COUNTEREXAMPLE_REJECTED: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
