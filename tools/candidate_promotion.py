"""Fail-closed promotion of a model-generated candidate into a synthetic-only worktree.

This module does not execute generated source, push branches, or merge PRs.
An independent authorized writer must separately handle GitHub operations.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import sys

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ALLOWED_NODE_TYPES = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg,
                      ast.Return, ast.Constant, ast.Expr, ast.Pass, ast.Load,
                      ast.Name, ast.BinOp, ast.Add, ast.Sub, ast.Mult)


def promote(candidate_path, receipt_path, destination, expected_run_id):
    candidate = Path(candidate_path).read_bytes()
    receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        raise ValueError("receipt must be an object")
    digest = receipt.get("candidate_sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError("missing canonical candidate digest")
    if not isinstance(expected_run_id, int) or expected_run_id <= 0:
        raise ValueError("invalid expected run ID")
    if type(receipt.get("run_id")) is not int or receipt["run_id"] != expected_run_id:
        raise ValueError("untrusted run provenance")
    if receipt.get("source_repository") != "THECHANJONG/project002-synthetic-pr-sandbox":
        raise ValueError("candidate outside synthetic sandbox")
    if receipt.get("model_executed") is not True:
        raise ValueError("no model execution attestation")
    if hashlib.sha256(candidate).hexdigest() != digest:
        raise ValueError("candidate digest mismatch")
    if not candidate or len(candidate) > 4096:
        raise ValueError("candidate size outside bounds")
    source = candidate.decode("utf-8", errors="strict")
    tree = ast.parse(source)
    if not tree.body or any(not isinstance(node, ast.FunctionDef) for node in tree.body):
        raise ValueError("only standalone functions allowed")
    if any(not isinstance(node, ALLOWED_NODE_TYPES) for node in ast.walk(tree)):
        raise ValueError("unsafe Python syntax")
    dest = Path(destination)
    if dest.name != "model_candidate.py" or dest.is_symlink():
        raise ValueError("destination not approved")
    if dest.parent.resolve() != (Path.cwd() / "synthetic").resolve():
        raise ValueError("destination outside synthetic fixture")
    dest.parent.mkdir(exist_ok=True)
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(candidate)
    return digest


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("usage: candidate_promotion.py CANDIDATE RECEIPT DESTINATION RUN_ID")
    print(promote(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])))
