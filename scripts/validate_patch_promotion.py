"""Fail-closed, offline validation of a bounded Actions patch artifact.

This validates artifact bytes against an independently supplied run identity and
current checkout. It does NOT authenticate the GitHub API run, authorize a PR,
prove scheduler origin, or grant any repository write capability.
"""
import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from scripts.prepare_patch_artifact import CODE, PROJECT_REPO, TARGET

SHA = re.compile(r"[0-9a-f]{40}\Z")
REQUIRED = frozenset({
    "schema_version", "project_id", "proof_scope", "repository", "event",
    "head_sha", "run_id", "run_attempt", "target", "candidate_status",
    "patch_sha256", "patch_bytes", "github_pr_opened", "github_main_merged",
    "scheduler_invocation_attestation", "independent_ai_cold_start",
    "remote_cas_lease_fencing",
})


class InvalidPromotion(ValueError):
    """Untrusted artifact is not eligible for promotion."""


def _no_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise InvalidPromotion("duplicate JSON key")
        obj[key] = value
    return obj


def _reject_constant(value):
    raise InvalidPromotion("non-finite JSON number")


def _regular_bytes(path, *, limit):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise InvalidPromotion("artifact member not a regular file")
    if path.stat().st_size > limit:
        raise InvalidPromotion("artifact member exceeds size limit")
    return path.read_bytes()


def _checkout_status(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise InvalidPromotion("checkout root not a real directory")
    parent = root / "generated"
    if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
        raise InvalidPromotion("target parent is not a real directory")
    target = root / TARGET
    if target.is_symlink():
        raise InvalidPromotion("target symlink rejected")
    if not os.path.lexists(target):
        return "CREATE_ONLY"
    if not target.is_file() or target.stat().st_size > 4096:
        raise InvalidPromotion("existing target is not a bounded file")
    try:
        existing = target.read_text(encoding="utf-8")
        if ast.dump(ast.parse(existing), include_attributes=False) != ast.dump(
                ast.parse(CODE), include_attributes=False):
            raise InvalidPromotion("existing code is not approved")
    except (SyntaxError, UnicodeError, RecursionError) as exc:
        raise InvalidPromotion("existing code cannot be parsed") from exc
    return "ALREADY_PRESENT"


def validate_artifact(artifact_dir, *, expected_head, expected_run_id,
                      expected_attempt, checkout_root):
    """Return offline consistency verdict; never writes to disk or GitHub."""
    if (type(expected_head) is not str or not SHA.fullmatch(expected_head)
            or type(expected_run_id) is not int or expected_run_id <= 0
            or type(expected_attempt) is not int or expected_attempt <= 0):
        raise InvalidPromotion("invalid externally expected provenance")
    directory = Path(artifact_dir)
    if directory.is_symlink() or not directory.is_dir():
        raise InvalidPromotion("artifact directory missing or symlinked")
    if {p.name for p in directory.iterdir()} != {"receipt.json", "candidate.patch"}:
        raise InvalidPromotion("unexpected artifact inventory")
    try:
        raw_receipt = _regular_bytes(directory / "receipt.json", limit=8192)
        patch = _regular_bytes(directory / "candidate.patch", limit=4096)
        receipt = json.loads(raw_receipt.decode("utf-8"),
                             object_pairs_hook=_no_duplicates,
                             parse_constant=_reject_constant)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise InvalidPromotion("artifact contents malformed") from exc
    if type(receipt) is not dict or set(receipt) != REQUIRED:
        raise InvalidPromotion("receipt schema mismatch")
    if (type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1
            or receipt["project_id"] != "PROJECT_002_SYNTHETIC"
            or receipt["proof_scope"] != "DETERMINISTIC_PATCH_ARTIFACT_ONLY"
            or receipt["repository"] != PROJECT_REPO
            or receipt["event"] not in ("push", "pull_request")
            or receipt["head_sha"] != expected_head
            or type(receipt["run_id"]) is not int or receipt["run_id"] != expected_run_id
            or type(receipt["run_attempt"]) is not int or receipt["run_attempt"] != expected_attempt
            or receipt["target"] != TARGET
            or receipt["github_pr_opened"] is not False
            or receipt["github_main_merged"] is not False
            or receipt["scheduler_invocation_attestation"] != "UNAVAILABLE"
            or receipt["independent_ai_cold_start"] != "NOT_PROVEN"
            or receipt["remote_cas_lease_fencing"] != "NOT_PROVEN"):
        raise InvalidPromotion("receipt provenance or scope mismatch")
    if (type(receipt["patch_bytes"]) is not int
            or receipt["patch_bytes"] != len(patch)
            or type(receipt["patch_sha256"]) is not str
            or receipt["patch_sha256"] != hashlib.sha256(patch).hexdigest()):
        raise InvalidPromotion("patch integrity mismatch")
    status = receipt["candidate_status"]
    if status not in ("CREATE_ONLY", "ALREADY_PRESENT"):
        raise InvalidPromotion("unknown candidate status")
    if status != _checkout_status(checkout_root):
        raise InvalidPromotion("candidate no longer matches checkout")
    if status == "CREATE_ONLY":
        expected_patch = "".join(difflib.unified_diff(
            [], CODE.splitlines(keepends=True), fromfile="/dev/null",
            tofile="b/" + TARGET)).encode("utf-8")
        if patch != expected_patch:
            raise InvalidPromotion("patch differs from allowlisted candidate")
    elif patch:
        raise InvalidPromotion("already-present candidate must have empty patch")
    return {
        "candidate_status": status,
        "patch_sha256": receipt["patch_sha256"],
        "offline_consistency": "VERIFIED",
        "github_run_api_attestation": "NOT_CHECKED",
        "pr_eligible_after_independent_run_check": status == "CREATE_ONLY",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline validation only; never authorizes PR/merge")
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--attempt", required=True, type=int)
    args = parser.parse_args(argv)
    result = validate_artifact(args.artifact, expected_head=args.expected_head,
                               expected_run_id=args.run_id, expected_attempt=args.attempt,
                               checkout_root=args.checkout)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
