"""Pure, fail-closed lease/fencing transitions for NON-AUTHORITATIVE synthetic state.

Callers MUST fetch GitHub's current file blob and submit the returned blob SHA
as the Contents API precondition. These guards are client-side: they cannot
prevent an untrusted client from bypassing validation, nor provide server-side
atomic fencing or independent-worker/crash-recovery proof.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class UnsafeTransition(ValueError):
    """A synthetic state mutation was rejected without modifying the input."""


def _utc_time(value):
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise UnsafeTransition("lease expiration must be canonical UTC seconds")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise UnsafeTransition("invalid lease expiration") from exc


def _validate(snapshot, *, current_blob_sha, expected_blob_sha,
              expected_revision, now):
    if (type(current_blob_sha) is not str or not _SHA.fullmatch(current_blob_sha)
            or type(expected_blob_sha) is not str or not _SHA.fullmatch(expected_blob_sha)
            or current_blob_sha != expected_blob_sha):
        raise UnsafeTransition("missing, malformed or stale GitHub blob precondition")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise UnsafeTransition("now must be timezone-aware UTC")
    if (not isinstance(snapshot, dict) or type(snapshot.get("schema_version")) is not int
            or snapshot["schema_version"] != 1):
        raise UnsafeTransition("unknown synthetic state schema")
    if snapshot.get("project_id") != "PROJECT_002_SYNTHETIC":
        raise UnsafeTransition("not a synthetic test state")
    revision = snapshot.get("revision")
    if (type(revision) is not int or revision < 0
            or type(expected_revision) is not int or expected_revision != revision):
        raise UnsafeTransition("invalid or stale state revision")
    lease = snapshot.get("lease")
    if not isinstance(lease, dict) or not isinstance(snapshot.get("records"), dict):
        raise UnsafeTransition("invalid lease or records")
    if (type(lease.get("owner")) is not str or not lease["owner"].strip()
            or type(lease.get("token")) is not int or lease["token"] < 1):
        raise UnsafeTransition("invalid lease owner or fencing token")
    return lease, _utc_time(lease.get("expires_at"))


def guarded_record_write(snapshot, *, current_blob_sha, expected_blob_sha,
                         expected_revision, worker_id, fencing_token, now,
                         record_key, value):
    """Return an updated copy only for the current unexpired lease holder."""
    lease, expires = _validate(snapshot, current_blob_sha=current_blob_sha,
                               expected_blob_sha=expected_blob_sha,
                               expected_revision=expected_revision, now=now)
    if (type(worker_id) is not str or worker_id != lease["owner"]
            or type(fencing_token) is not int or fencing_token != lease["token"]):
        raise UnsafeTransition("stale worker or fencing token")
    if now >= expires:
        raise UnsafeTransition("lease expired")
    if type(record_key) is not str or not record_key:
        raise UnsafeTransition("invalid record key")
    updated = deepcopy(snapshot)
    updated["revision"] += 1
    updated["records"][record_key] = deepcopy(value)
    return updated


def guarded_expired_takeover(snapshot, *, current_blob_sha, expected_blob_sha,
                             expected_revision, new_owner, now, ttl_seconds):
    """Return a fenced takeover proposal; caller must still GitHub-CAS write."""
    lease, expires = _validate(snapshot, current_blob_sha=current_blob_sha,
                               expected_blob_sha=expected_blob_sha,
                               expected_revision=expected_revision, now=now)
    if now < expires:
        raise UnsafeTransition("cannot steal an unexpired lease")
    if (type(new_owner) is not str or not new_owner.strip()
            or new_owner == lease["owner"]):
        raise UnsafeTransition("takeover requires a different valid owner")
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 3600:
        raise UnsafeTransition("invalid bounded lease duration")
    updated = deepcopy(snapshot)
    updated["revision"] += 1
    updated["lease"] = {
        "owner": new_owner,
        "token": lease["token"] + 1,
        "expires_at": (now + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return updated
