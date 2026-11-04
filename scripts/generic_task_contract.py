"""Portable, fail-closed task contract for a future AI coding worker.

This validates a task request only. It does NOT execute a model, run commands,
write to a repository, authorize a merge, or attest scheduler provenance.
"""
import json
import math
import re

class InvalidTask(ValueError):
    pass

_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\\Z")
_SHA = re.compile(r"[0-9a-f]{40}\\Z")
_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\\Z")
_ALLOWED = {"schema_version", "task_id", "repository", "base_sha", "objective", "allowed_paths", "acceptance_tests"}

def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidTask("duplicate JSON key")
        result[key] = value
    return result

def _reject_constant(value):
    raise InvalidTask("nonfinite JSON number")

def parse_task(raw):
    if type(raw) is not str or len(raw.encode("utf-8")) > 32768:
        raise InvalidTask("task must be bounded UTF-8 JSON text")
    try:
        obj = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except (ValueError, RecursionError, OverflowError) as exc:
        raise InvalidTask("invalid task JSON") from exc
    if type(obj) is not dict or set(obj) != _ALLOWED:
        raise InvalidTask("unexpected or missing task fields")
    if type(obj["schema_version"]) is not int or obj["schema_version"] != 1:
        raise InvalidTask("unsupported task schema")
    if type(obj["task_id"]) is not str or not _ID.fullmatch(obj["task_id"]):
        raise InvalidTask("invalid task id")
    if type(obj["repository"]) is not str or not _REPO.fullmatch(obj["repository"]) or ".." in obj["repository"]:
        raise InvalidTask("invalid repository")
    if type(obj["base_sha"]) is not str or not _SHA.fullmatch(obj["base_sha"]):
        raise InvalidTask("base SHA must be pinned")
    if type(obj["objective"]) is not str or not 10 <= len(obj["objective"].strip()) <= 2000:
        raise InvalidTask("objective missing or unbounded")
    paths = obj["allowed_paths"]
    if type(paths) is not list or not 1 <= len(paths) <= 32:
        raise InvalidTask("allowed paths must be bounded")
    for path in paths:
        if (type(path) is not str or not 1 <= len(path) <= 200
                or path.startswith("/") or "\\" in path or "//" in path
                or any(segment in ("", ".", "..") for segment in path.split("/"))
                or any(ord(c) < 32 for c in path)):
            raise InvalidTask("unsafe allowed path")
    if len(set(paths)) != len(paths):
        raise InvalidTask("duplicate allowed path")
    tests = obj["acceptance_tests"]
    if type(tests) is not list or not 1 <= len(tests) <= 16:
        raise InvalidTask("acceptance tests must be bounded")
    for test in tests:
        if type(test) is not str or not 1 <= len(test.strip()) <= 300:
            raise InvalidTask("invalid acceptance test")
    if len(set(tests)) != len(tests):
        raise InvalidTask("duplicate acceptance test")
    return obj
