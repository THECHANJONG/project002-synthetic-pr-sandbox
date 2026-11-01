"""Pure negative controls; NOT an independent GitHub worker E2E test."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import unittest

from scripts.fenced_state import (
    UnsafeTransition, guarded_record_write, guarded_expired_takeover,
)

SHA = "a" * 40
NEXT_SHA = "b" * 40
T0 = datetime(2026, 11, 1, 10, 5, tzinfo=timezone.utc)


def snapshot():
    return {
        "schema_version": 1,
        "project_id": "PROJECT_002_SYNTHETIC",
        "revision": 2,
        "lease": {"owner": "worker-B", "token": 2,
                  "expires_at": "2026-11-01T10:09:00Z"},
        "records": {},
    }


def write(state, **overrides):
    args = dict(current_blob_sha=SHA, expected_blob_sha=SHA,
                expected_revision=state["revision"], worker_id="worker-B",
                fencing_token=2, now=T0, record_key="x", value={"ok": True})
    args.update(overrides)
    return guarded_record_write(state, **args)


def takeover(state, **overrides):
    args = dict(current_blob_sha=SHA, expected_blob_sha=SHA,
                expected_revision=state["revision"], new_owner="worker-C",
                now=datetime(2026, 11, 1, 10, 10, tzinfo=timezone.utc),
                ttl_seconds=60)
    args.update(overrides)
    return guarded_expired_takeover(state, **args)


class FencingTransitions(unittest.TestCase):
    def rejected_write(self, **overrides):
        original = snapshot()
        before = deepcopy(original)
        with self.assertRaises(UnsafeTransition):
            write(original, **overrides)
        self.assertEqual(original, before)

    def test_valid_record_write_is_copy_only(self):
        original = snapshot()
        result = write(original)
        self.assertEqual(original["revision"], 2)
        self.assertEqual(original["records"], {})
        self.assertEqual(result["revision"], 3)
        self.assertEqual(result["records"], {"x": {"ok": True}})

    def test_stale_token_even_with_fresh_blob_is_rejected(self):
        self.rejected_write(fencing_token=1)

    def test_stale_owner_even_with_fresh_blob_is_rejected(self):
        self.rejected_write(worker_id="worker-A")

    def test_stale_blob_is_rejected(self):
        self.rejected_write(current_blob_sha=NEXT_SHA)

    def test_stale_revision_is_rejected(self):
        self.rejected_write(expected_revision=1)

    def test_boolean_token_is_rejected(self):
        self.rejected_write(fencing_token=True)

    def test_expired_holder_is_rejected(self):
        self.rejected_write(now=datetime(2026, 11, 1, 10, 9, tzinfo=timezone.utc))

    def test_naive_time_is_rejected(self):
        self.rejected_write(now=datetime(2026, 11, 1, 10, 5))

    def test_malformed_lease_is_rejected(self):
        state = snapshot()
        state["lease"]["expires_at"] = "not-a-date"
        with self.assertRaises(UnsafeTransition):
            write(state)

    def test_boolean_schema_version_is_rejected(self):
        state = snapshot()
        state["schema_version"] = True
        with self.assertRaises(UnsafeTransition):
            write(state)

    def test_wrong_project_is_rejected(self):
        state = snapshot()
        state["project_id"] = "PROJECT_002"
        with self.assertRaises(UnsafeTransition):
            write(state)

    def test_takeover_before_expiration_is_rejected(self):
        with self.assertRaises(UnsafeTransition):
            takeover(snapshot(), now=T0)

    def test_takeover_requires_new_owner(self):
        with self.assertRaises(UnsafeTransition):
            takeover(snapshot(), new_owner="worker-B")

    def test_takeover_rejects_boolean_ttl(self):
        with self.assertRaises(UnsafeTransition):
            takeover(snapshot(), ttl_seconds=True)

    def test_takeover_advances_token_and_revision_without_mutation(self):
        state = snapshot()
        updated = takeover(state)
        self.assertEqual(state["lease"]["token"], 2)
        self.assertEqual(updated["lease"], {
            "owner": "worker-C", "token": 3,
            "expires_at": "2026-11-01T10:11:00Z",
        })
        self.assertEqual(updated["revision"], 3)

    def test_old_worker_cannot_write_after_takeover_with_fresh_sha(self):
        updated = takeover(snapshot())
        with self.assertRaises(UnsafeTransition):
            write(updated, current_blob_sha=NEXT_SHA, expected_blob_sha=NEXT_SHA,
                  expected_revision=3, worker_id="worker-B", fencing_token=2,
                  now=datetime(2026, 11, 1, 10, 10, 30, tzinfo=timezone.utc))
        accepted = write(updated, current_blob_sha=NEXT_SHA, expected_blob_sha=NEXT_SHA,
                         expected_revision=3, worker_id="worker-C", fencing_token=3,
                         now=datetime(2026, 11, 1, 10, 10, 30, tzinfo=timezone.utc))
        self.assertEqual(accepted["revision"], 4)


if __name__ == "__main__":
    unittest.main()
