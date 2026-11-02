"""Create a bounded, idempotent synthetic patch artifact on a read-only runner.

No AI authoring, GitHub PR/merge, remote lease or scheduler-origin proof.
Existing equivalent code is a verified NO_CHANGE, never a second add-file patch.
"""
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{40}\Z")
PROJECT_REPO = "THECHANJONG/project002-synthetic-pr-sandbox"
TARGET = "generated/phase1_worker_probe.py"
CODE = (
    '# Synthetic bounded code candidate; not deployed or merged.\n'
    'PROJECT_ID = "PROJECT_002_SYNTHETIC"\n'
    'EXECUTOR = "github-actions-readonly"\n'
)


class InvalidProvenance(ValueError):
    pass


def _candidate(checkout_root):
    target = Path(checkout_root) / TARGET
    if target.is_symlink():
        raise InvalidProvenance("target symlink rejected")
    if not target.exists():
        return "CREATE_ONLY", "".join(difflib.unified_diff(
            [], CODE.splitlines(keepends=True),
            fromfile="/dev/null", tofile="b/" + TARGET,
        ))
    if not target.is_file() or target.stat().st_size > 4096:
        raise InvalidProvenance("existing target is not a bounded regular file")
    try:
        existing = target.read_text(encoding="utf-8")
        if ast.dump(ast.parse(existing), include_attributes=False) != ast.dump(
                ast.parse(CODE), include_attributes=False):
            raise InvalidProvenance("existing target differs from approved code")
    except (SyntaxError, UnicodeError) as exc:
        raise InvalidProvenance("existing target cannot be validated") from exc
    return "ALREADY_PRESENT", ""


def prepare(env, *, output_dir, checkout_root="."):
    """Return receipt and immutable candidate artifact without changing checkout."""
    if env.get("GITHUB_REPOSITORY") != PROJECT_REPO:
        raise InvalidProvenance("wrong repository")
    expected = env.get("EXPECTED_HEAD")
    actual = env.get("CHECKED_OUT_HEAD")
    if (type(expected) is not str or not SHA.fullmatch(expected)
            or actual != expected):
        raise InvalidProvenance("checkout SHA does not match event HEAD")
    event = env.get("GITHUB_EVENT_NAME")
    if event not in ("push", "pull_request"):
        raise InvalidProvenance("unsupported event")
    if event == "push" and env.get("GITHUB_REF") != "refs/heads/main":
        raise InvalidProvenance("only main pushes are eligible")
    if event == "pull_request" and not re.fullmatch(
            r"refs/pull/[1-9][0-9]*/merge", env.get("GITHUB_REF", "")):
        raise InvalidProvenance("invalid PR event ref")
    run_id = env.get("GITHUB_RUN_ID", "")
    attempt = env.get("GITHUB_RUN_ATTEMPT", "")
    if (not re.fullmatch(r"[1-9][0-9]*", run_id)
            or not re.fullmatch(r"[1-9][0-9]*", attempt)):
        raise InvalidProvenance("invalid GitHub run identity")
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise InvalidProvenance("artifact output directory not empty")
    status, patch = _candidate(checkout_root)
    if len(patch.encode("utf-8")) > 4096:
        raise InvalidProvenance("patch exceeds bounded size")
    receipt = {
        "schema_version": 1,
        "project_id": "PROJECT_002_SYNTHETIC",
        "proof_scope": "DETERMINISTIC_PATCH_ARTIFACT_ONLY",
        "repository": PROJECT_REPO,
        "event": event,
        "head_sha": expected,
        "run_id": int(run_id),
        "run_attempt": int(attempt),
        "target": TARGET,
        "candidate_status": status,
        "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
        "patch_bytes": len(patch.encode("utf-8")),
        "github_pr_opened": False,
        "github_main_merged": False,
        "scheduler_invocation_attestation": "UNAVAILABLE",
        "independent_ai_cold_start": "NOT_PROVEN",
        "remote_cas_lease_fencing": "NOT_PROVEN",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "candidate.patch").write_text(patch, encoding="utf-8")
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def main():
    receipt = prepare(os.environ, output_dir="phase1-patch-evidence")
    print("SYNTHETIC_PATCH_PREPARED=" + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
