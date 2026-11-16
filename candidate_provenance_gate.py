"""Fail-closed verification before promoting a model-generated candidate.

This module does not write to GitHub or execute candidate source.
The manifest is untrusted; callers must independently bind the run ID and
head SHA to GitHub's API before using the verified bytes.
"""
import ast
import hashlib
import re

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_RUN = re.compile(r"[1-9][0-9]*\Z")

class CandidateRejected(ValueError):
    pass

def verify_candidate(source: bytes, manifest: dict, *, expected_run_id: int,
                     expected_head_sha: str) -> str:
    """Return validated UTF-8 source; never execute it."""
    if not isinstance(source, bytes) or not source or len(source) > 4096:
        raise CandidateRejected("invalid candidate size")
    if not isinstance(manifest, dict) or set(manifest) != {
        "run_id", "head_sha", "sha256", "path"
    }:
        raise CandidateRejected("invalid manifest schema")
    if type(expected_run_id) is not int or expected_run_id <= 0:
        raise CandidateRejected("invalid expected run")
    if not isinstance(expected_head_sha, str) or not _SHA.fullmatch(expected_head_sha):
        raise CandidateRejected("invalid expected head")
    run_id = manifest["run_id"]
    if not isinstance(run_id, str) or not _RUN.fullmatch(run_id) or int(run_id) != expected_run_id:
        raise CandidateRejected("run mismatch")
    if manifest["head_sha"] != expected_head_sha:
        raise CandidateRejected("head mismatch")
    digest = manifest["sha256"]
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise CandidateRejected("invalid digest")
    if hashlib.sha256(source).hexdigest() != digest:
        raise CandidateRejected("digest mismatch")
    if manifest["path"] != "generated/candidate.py":
        raise CandidateRejected("path not allowlisted")
    try:
        text = source.decode("utf-8", errors="strict")
        tree = ast.parse(text)
    except (UnicodeError, SyntaxError, ValueError) as exc:
        raise CandidateRejected("invalid Python") from exc
    # Narrow data-only candidate contract: one function returning a literal.
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise CandidateRejected("unexpected top-level code")
    fn = tree.body[0]
    if fn.name != "generated_value" or fn.decorator_list or fn.args.args or fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.vararg or fn.args.kwarg or fn.args.defaults or fn.args.kw_defaults:
        raise CandidateRejected("unexpected function signature")
    if len(fn.body) != 1 or not isinstance(fn.body[0], ast.Return):
        raise CandidateRejected("unexpected function body")
    value = fn.body[0].value
    if not isinstance(value, ast.Constant) or type(value.value) not in (str, int, bool, type(None)):
        raise CandidateRejected("nonliteral return")
    return text
