"""No-network CAS transport and fencing controls; NOT independent remote workers."""
import base64
import json
import unittest
from datetime import datetime, timezone
from urllib.error import HTTPError

from scripts.github_cas_worker import (
    Client, Blocked, Conflict, _blob_sha, transition, URL, BRANCH, PATH,
)

NOW = datetime(2026, 11, 3, 7, 0, tzinfo=timezone.utc)


def state():
    return {"schema_version": 1, "project_id": "PROJECT_002_SYNTHETIC",
            "revision": 2, "lease": {"owner": "worker-a", "token": 2,
            "expires_at": "2026-11-03T06:59:00Z"}, "records": {}}


class Reply:
    def __init__(self, url, data):
        self.url, self.data = url, data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None
    def geturl(self):
        return self.url
    def read(self, n):
        return self.data[:n]


class Server:
    def __init__(self):
        self.state = state()
        self.requests = []
        self.reject = False
        self.redirect = False
        self.tamper = False

    def __call__(self, request, timeout):
        self.requests.append(request)
        url = request.full_url
        if request.get_method() == "GET":
            raw = json.dumps(self.state, sort_keys=True, separators=(",", ":")).encode()
            body = {"type": "file", "path": PATH, "encoding": "base64",
                    "sha": _blob_sha(raw), "content": base64.b64encode(raw).decode()}
        else:
            payload = json.loads(request.data)
            old = json.dumps(self.state, sort_keys=True, separators=(",", ":")).encode()
            if self.reject or payload["sha"] != _blob_sha(old):
                raise HTTPError(url, 409, "conflict", {}, None)
            raw = base64.b64decode(payload["content"])
            self.state = json.loads(raw)
            body = {"content": {"sha": _blob_sha(raw)}, "commit": {"sha": "b" * 40}}
            if self.tamper:
                body["content"]["sha"] = "c" * 40
        return Reply("https://evil.example" if self.redirect else url,
                     json.dumps(body).encode())


class CASWorkerTests(unittest.TestCase):
    def test_takeover_then_append_and_stale_holder_denied(self):
        server = Server()
        client = Client("synthetic-token", opener=server)
        a = transition(client, operation="takeover", owner="worker-b", now=NOW)
        self.assertEqual(a["token"], 3)
        b = transition(client, operation="write", owner="worker-b", token=3,
                       record_key="receipt-1", value={"safe": True}, now=NOW)
        self.assertEqual(b["revision"], 4)
        with self.assertRaises(Blocked):
            transition(client, operation="write", owner="worker-a", token=2,
                       record_key="receipt-2", value={"bad": True}, now=NOW)
        self.assertEqual(server.state["records"], {"receipt-1": {"safe": True}})
        self.assertTrue(all("Authorization" not in req.headers for req in server.requests))
        self.assertTrue(all("Authorization" in req.unredirected_hdrs for req in server.requests))

    def test_stale_precondition_fails_closed_no_retry(self):
        server = Server()
        server.reject = True
        with self.assertRaises(Conflict):
            transition(Client("synthetic-token", opener=server),
                       operation="takeover", owner="worker-b", now=NOW)
        self.assertEqual(len(server.requests), 2)
        self.assertEqual(server.state["revision"], 2)

    def test_duplicate_receipt_never_overwritten(self):
        server = Server()
        server.state["lease"] = {"owner": "worker-b", "token": 3,
                                 "expires_at": "2026-11-03T07:01:00Z"}
        server.state["records"] = {"receipt-1": {"safe": True}}
        with self.assertRaises(Blocked):
            transition(Client("synthetic-token", opener=server),
                       operation="write", owner="worker-b", token=3,
                       record_key="receipt-1", value={"safe": False}, now=NOW)
        self.assertEqual(len(server.requests), 1)

    def test_malformed_token_denied(self):
        for token in (None, "", "bad\nheader", 123):
            with self.subTest(token=repr(token)), self.assertRaises(Blocked):
                Client(token)

    def test_redirect_denied(self):
        server = Server()
        server.redirect = True
        with self.assertRaises(Blocked):
            Client("synthetic-token", opener=server).read()

    def test_write_acknowledgment_tamper_denied(self):
        server = Server()
        server.tamper = True
        with self.assertRaises(Blocked):
            transition(Client("synthetic-token", opener=server),
                       operation="takeover", owner="worker-b", now=NOW)

    def test_read_blob_tamper_denied(self):
        server = Server()
        def corrupt(req, timeout):
            response = server(req, timeout)
            body = json.loads(response.data)
            body["sha"] = "0" * 40
            return Reply(response.url, json.dumps(body).encode())
        with self.assertRaises(Blocked):
            Client("synthetic-token", opener=corrupt).read()

    def test_api_target_is_isolated(self):
        self.assertEqual(BRANCH, "state/phase1-cas-live-test")
        self.assertNotIn("ai-quality-control-system", URL)
        self.assertNotIn("main", BRANCH)


if __name__ == "__main__":
    unittest.main()
