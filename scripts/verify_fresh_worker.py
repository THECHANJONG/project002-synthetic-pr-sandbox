"""Read-only, context-free handoff drill against a PUBLIC SYNTHETIC entrypoint.

This proves deterministic reconstruction in a fresh process, NOT an independent
AI cold start, scheduler provenance, external CAS, or production readiness.
"""
import json
import os
import re
import sys
from pathlib import Path

REPO = "THECHANJONG/project002-synthetic-pr-sandbox"
WORKFLOW = "phase1-fresh-worker-readonly"
ENTRYPOINT = Path(__file__).resolve().parents[1] / "handoff/SYNTHETIC_ENTRYPOINT.json"
SHA = re.compile(r"[0-9a-f]{40}\Z")
POSITIVE = re.compile(r"[1-9][0-9]{0,19}\Z")
MANIFEST = {
    "schema_version": 1,
    "project_id": "PROJECT_002",
    "repository": REPO,
    "phase": "PHASE_1",
    "authority": "NON_AUTHORITATIVE_SYNTHETIC_ONLY",
    "read_only_task": "VERIFY_REMOTE_HEAD_AND_REPORT_LIMITS",
    "source_ref": "GITHUB_EVENT_HEAD",
    "scheduler_invocation_attestation": "UNAVAILABLE",
    "official_notion_pointer": "NOT_INCLUDED",
    "write_authorized": False,
}


class UnsafeHandoff(ValueError):
    pass


def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise UnsafeHandoff("duplicate manifest key")
        out[key] = value
    return out


def reject_constant(value):
    raise UnsafeHandoff("non-JSON constant")


def verify_manifest(raw):
    if type(raw) is not str:
        raise UnsafeHandoff("manifest must be text")
    try:
        manifest = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    except (ValueError, TypeError) as exc:
        raise UnsafeHandoff("invalid manifest: " + str(exc)) from exc
    if type(manifest) is not dict or set(manifest) != set(MANIFEST):
        raise UnsafeHandoff("manifest schema drift")
    for key, expected in MANIFEST.items():
        actual = manifest[key]
        if type(actual) is not type(expected) or actual != expected:
            raise UnsafeHandoff("unsafe manifest field: " + key)
    return manifest


def verify_environment(env):
    if type(env) is not dict:
        raise UnsafeHandoff("environment must be object")
    if env.get("GITHUB_REPOSITORY") != REPO or env.get("GITHUB_WORKFLOW") != WORKFLOW:
        raise UnsafeHandoff("wrong repository or workflow")
    event = env.get("GITHUB_EVENT_NAME")
    ref = env.get("REMOTE_REF")
    if event == "push":
        if ref != "refs/heads/main":
            raise UnsafeHandoff("unexpected push ref")
    elif event == "pull_request":
        if type(ref) is not str or not re.fullmatch(r"refs/pull/[1-9][0-9]*/head", ref):
            raise UnsafeHandoff("unexpected PR ref")
    else:
        raise UnsafeHandoff("unapproved event")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        value = env.get(key)
        if type(value) is not str or not POSITIVE.fullmatch(value):
            raise UnsafeHandoff("invalid " + key)
    expected = env.get("EXPECTED_HEAD")
    for key in ("CHECKED_OUT_HEAD", "REMOTE_HEAD"):
        actual = env.get(key)
        if (type(expected) is not str or not SHA.fullmatch(expected)
                or type(actual) is not str or not SHA.fullmatch(actual)
                or actual != expected):
            raise UnsafeHandoff("exact head mismatch: " + key)
    return {
        "status": "FRESH_PROCESS_READ_ONLY_RECONSTRUCTION",
        "repository": REPO,
        "verified_head": expected,
        "remote_ref": ref,
        "run_id": env["GITHUB_RUN_ID"],
        "run_attempt": env["GITHUB_RUN_ATTEMPT"],
        "independent_ai_cold_start": "NOT_PROVEN",
        "scheduler_invocation_attestation": "UNAVAILABLE",
        "shared_remote_cas_lease_fencing": "NOT_PROVEN",
        "official_pointer": "NOT_INCLUDED",
        "mutable_authority": "NOT_GRANTED",
    }


def main():
    try:
        verify_manifest(ENTRYPOINT.read_text(encoding="utf-8"))
        result = verify_environment(dict(os.environ))
    except (OSError, UnsafeHandoff) as exc:
        print("FRESH_WORKER_REJECTED: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
