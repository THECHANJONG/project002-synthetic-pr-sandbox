"""Synthetic-only GitHub Contents CAS worker; never targets original or main.

Candidate transport only: no new Actions permissions or scheduled write execution.
Real two-runner remote fencing, clock agreement, and cold start remain NOT PROVEN.
"""
import argparse
import base64
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from scripts.fenced_state import (UnsafeTransition, guarded_expired_takeover,
                                  guarded_record_write)

REPO = "THECHANJONG/project002-synthetic-pr-sandbox"
BRANCH = "state/phase1-cas-live-test"
PATH = "handoff/SYNTHETIC_CAS_LIVE.json"
URL = "https://api.github.com/repos/" + REPO + "/contents/" + PATH
SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_BYTES = 131072


class Blocked(RuntimeError):
    pass


class Conflict(Blocked):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Blocked("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_):
    raise Blocked("nonfinite JSON")


def _finite_float(s):
    value = float(s)
    if not math.isfinite(value):
        raise Blocked("nonfinite JSON")
    return value


def _decode(raw):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=_reject_constant, parse_float=_finite_float)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise Blocked("invalid JSON response") from exc


def _blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


class Client:
    def __init__(self, token, opener=urlopen):
        if type(token) is not str or not token.strip() or "\r" in token or "\n" in token:
            raise Blocked("authorized token unavailable")
        self._token = token
        self._opener = opener

    def _call(self, method, body=None):
        if method not in ("GET", "PUT"):
            raise Blocked("unsupported operation")
        payload = (None if body is None else json.dumps(body, sort_keys=True,
                   separators=(",", ":"), allow_nan=False).encode("utf-8"))
        url = URL + ("?ref=" + quote(BRANCH, safe="") if method == "GET" else "")
        req = Request(url, data=payload, method=method, headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "project002-synthetic-cas-worker",
        })
        req.add_unredirected_header("Authorization", "Bearer " + self._token)
        try:
            with self._opener(req, timeout=15) as response:
                if response.geturl() != url:
                    raise Blocked("unexpected API redirect")
                raw = response.read(MAX_BYTES + 1)
        except HTTPError as exc:
            if method == "PUT" and exc.code in (409, 422):
                raise Conflict("remote CAS rejected") from None
            raise Blocked("GitHub API request failed") from None
        except (URLError, OSError, TimeoutError) as exc:
            raise Blocked("GitHub API unavailable") from exc
        if len(raw) > MAX_BYTES:
            raise Blocked("oversized GitHub response")
        result = _decode(raw)
        if type(result) is not dict:
            raise Blocked("unexpected API response")
        return result

    def read(self):
        info = self._call("GET")
        if (info.get("type") != "file" or info.get("path") != PATH
                or info.get("encoding") != "base64"
                or type(info.get("sha")) is not str
                or not SHA.fullmatch(info["sha"])):
            raise Blocked("wrong state file identity")
        content = info.get("content")
        if type(content) is not str:
            raise Blocked("missing state bytes")
        try:
            raw = base64.b64decode("".join(content.split()), validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise Blocked("invalid state base64") from exc
        if len(raw) > MAX_BYTES or _blob_sha(raw) != info["sha"]:
            raise Blocked("state blob integrity mismatch")
        state = _decode(raw)
        if (type(state) is not dict or state.get("project_id") != "PROJECT_002_SYNTHETIC"
                or type(state.get("revision")) is not int or state["revision"] < 0):
            raise Blocked("not an initialized synthetic state")
        return info["sha"], state

    def put(self, expected_blob, state):
        if type(expected_blob) is not str or not SHA.fullmatch(expected_blob):
            raise Blocked("invalid expected blob")
        raw = (json.dumps(state, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8"))
        if len(raw) > MAX_BYTES:
            raise Blocked("state too large")
        response = self._call("PUT", {
            "message": "test(phase1): synthetic fenced CAS transition",
            "content": base64.b64encode(raw).decode("ascii"),
            "sha": expected_blob, "branch": BRANCH,
        })
        if (type(response.get("content")) is not dict
                or response["content"].get("sha") != _blob_sha(raw)
                or type(response.get("commit")) is not dict
                or type(response["commit"].get("sha")) is not str
                or not SHA.fullmatch(response["commit"]["sha"])):
            raise Blocked("write acknowledgment lacks integrity")
        confirmed_blob, confirmed = self.read()
        if confirmed_blob != _blob_sha(raw) or confirmed != state:
            raise Blocked("post-write readback mismatch")
        return response["commit"]["sha"]


def transition(client, *, operation, owner, token=None, record_key=None,
               value=None, ttl_seconds=60, now=None):
    """Single attempt: read, validate, conditional PUT, readback. No blind retry."""
    if now is None:
        now = datetime.now(timezone.utc)
    blob, state = client.read()
    common = dict(current_blob_sha=blob, expected_blob_sha=blob,
                  expected_revision=state["revision"], now=now)
    try:
        if operation == "takeover":
            proposed = guarded_expired_takeover(
                state, new_owner=owner, ttl_seconds=ttl_seconds, **common)
        elif operation == "write":
            proposed = guarded_record_write(
                state, worker_id=owner, fencing_token=token,
                record_key=record_key, value=value, **common)
        else:
            raise Blocked("unknown operation")
    except UnsafeTransition as exc:
        raise Blocked("fencing guard rejected: " + str(exc)) from exc
    commit = client.put(blob, proposed)
    return {"result": "SYNTHETIC_CAS_COMMITTED", "commit_sha": commit,
            "revision": proposed["revision"], "token": proposed["lease"]["token"],
            "scope": "SINGLE_REMOTE_GITHUB_CONTENTS_FILE_ONLY",
            "independent_workers": "NOT_PROVEN", "authoritative_run": "UNCHANGED"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("takeover", "write"))
    parser.add_argument("--owner", required=True)
    parser.add_argument("--token", type=int)
    parser.add_argument("--record-key")
    parser.add_argument("--ttl-seconds", type=int, default=60)
    args = parser.parse_args()
    try:
        result = transition(Client(os.environ.get("GITHUB_TOKEN")),
                            operation=args.operation, owner=args.owner,
                            token=args.token, record_key=args.record_key,
                            value={"synthetic": True}, ttl_seconds=args.ttl_seconds)
    except (Blocked, ValueError, KeyError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": type(exc).__name__}))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
