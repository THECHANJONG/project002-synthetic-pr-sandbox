"""Read-only evidence validator for distinct GitHub-hosted runner boots.

This checks that two independent jobs ran on different Linux boot identities
and checked out the same exact commit. It does NOT prove shared durable CAS,
distributed fencing, or independent AI cold start.
"""
import json
import os
import re
import sys
from uuid import UUID

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,127}\Z")


class InvalidRunnerEvidence(ValueError):
    pass


def _boot_id(value):
    if not isinstance(value, str):
        raise InvalidRunnerEvidence("boot id must be text")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise InvalidRunnerEvidence("invalid boot id") from exc
    if str(parsed) != value.lower() or parsed.int == 0:
        raise InvalidRunnerEvidence("noncanonical or zero boot id")
    return str(parsed)


def verify_two_hosts(first, second, expected_head):
    if not isinstance(expected_head, str) or not SHA40.fullmatch(expected_head):
        raise InvalidRunnerEvidence("expected head must be full lowercase SHA")
    boots = []
    hosts = []
    for record in (first, second):
        if not isinstance(record, dict):
            raise InvalidRunnerEvidence("runner evidence must be an object")
        if record.get("head_sha") != expected_head:
            raise InvalidRunnerEvidence("runner did not verify exact head")
        hostname = record.get("hostname")
        if not isinstance(hostname, str) or not HOST.fullmatch(hostname):
            raise InvalidRunnerEvidence("missing or invalid hostname")
        hosts.append(hostname)
        boots.append(_boot_id(record.get("boot_id")))
    if boots[0] == boots[1]:
        raise InvalidRunnerEvidence("same Linux boot identity: independent hosts not proven")
    return {
        "result": "TWO_DISTINCT_LINUX_BOOT_IDS_VERIFIED",
        "exact_head": expected_head,
        "hosts": hosts,
        "boot_ids": boots,
        "scope": "TWO_READ_ONLY_GITHUB_ACTIONS_JOBS_ONLY",
        "shared_durable_cas": "NOT_PROVEN",
        "distributed_fencing": "NOT_PROVEN",
        "independent_ai_cold_start": "NOT_PROVEN",
    }


def main():
    try:
        first = {key: os.environ["HOST_A_" + key.upper()] for key in ("boot_id", "hostname", "head_sha")}
        second = {key: os.environ["HOST_B_" + key.upper()] for key in ("boot_id", "hostname", "head_sha")}
        proof = verify_two_hosts(first, second, os.environ["EXPECTED_HEAD"])
    except (InvalidRunnerEvidence, KeyError) as exc:
        print("RUNNER_EVIDENCE_FAILED: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
