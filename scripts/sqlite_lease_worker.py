"""Isolated SQLite transactional lease test adapter; NOT production authority.

All state and fencing checks occur inside BEGIN IMMEDIATE. This is an
independent-process, single-runner experiment; no GitHub/Notion authority,
distributed clock guarantees, or scheduler provenance is claimed.
"""
import argparse
import json
import os
import sqlite3
import sys
import time


class Rejected(Exception):
    pass


def connect(path):
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    db.execute("PRAGMA busy_timeout=5000")
    return db


def init(path):
    with connect(path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS lease_state (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            project TEXT NOT NULL, revision INTEGER NOT NULL,
            owner TEXT NOT NULL, token INTEGER NOT NULL,
            expires_ns INTEGER NOT NULL, records TEXT NOT NULL
        )""")
        db.execute(
            "INSERT OR IGNORE INTO lease_state VALUES (1, ?, 0, '', 0, 0, '{}')",
            ("PROJECT_002_SYNTHETIC",),
        )


def snapshot(db):
    row = db.execute(
        "SELECT project, revision, owner, token, expires_ns, records "
        "FROM lease_state WHERE id=1"
    ).fetchone()
    if not row or row[0] != "PROJECT_002_SYNTHETIC":
        raise Rejected("missing or wrong synthetic authority")
    return dict(project=row[0], revision=row[1], owner=row[2],
                token=row[3], expires_ns=row[4], records=json.loads(row[5]))


def change(path, op, *, owner="", token=0, revision=-1, ttl_ms=1000, key=""):
    db = connect(path)
    try:
        db.execute("BEGIN IMMEDIATE")
        state = snapshot(db)
        now = time.time_ns()
        if op == "acquire":
            if not owner or ttl_ms < 500 or ttl_ms > 5000:
                raise Rejected("invalid owner or bounded TTL")
            if state["owner"] and now < state["expires_ns"]:
                raise Rejected("live lease held")
            state["owner"] = owner
            state["token"] += 1
            state["expires_ns"] = now + ttl_ms * 1_000_000
            state["revision"] += 1
        elif op in ("write", "crash"):
            if (not owner or owner != state["owner"] or type(token) is not int
                    or token != state["token"] or now >= state["expires_ns"]
                    or type(revision) is not int or revision != state["revision"]):
                raise Rejected("stale lease, fencing token or revision")
            if not key:
                raise Rejected("empty record key")
            # Enforce append-only receipts inside the same SQLite transaction
            # as the lease/revision check. Never silently overwrite on retry.
            if key in state["records"]:
                raise Rejected("receipt key already exists; read back instead")
            state["records"][key] = owner
            state["revision"] += 1
        else:
            raise Rejected("unknown operation")
        db.execute(
            "UPDATE lease_state SET revision=?, owner=?, token=?, "
            "expires_ns=?, records=? WHERE id=1",
            (state["revision"], state["owner"], state["token"],
             state["expires_ns"], json.dumps(state["records"], sort_keys=True)),
        )
        if op == "crash":
            # Deliberate process death AFTER uncommitted mutation.
            # SQLite must roll back the transaction on process exit.
            os._exit(71)
        db.commit()
        return state
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("operation", choices=("init", "inspect", "acquire", "write", "crash"))
    p.add_argument("db")
    p.add_argument("--owner", default="")
    p.add_argument("--token", type=int, default=0)
    p.add_argument("--revision", type=int, default=-1)
    p.add_argument("--ttl-ms", type=int, default=1000)
    p.add_argument("--key", default="")
    a = p.parse_args(argv)
    try:
        if a.operation == "init":
            init(a.db)
            result = {"initialized": True}
        elif a.operation == "inspect":
            with connect(a.db) as db:
                result = snapshot(db)
        else:
            result = change(a.db, a.operation, owner=a.owner, token=a.token,
                            revision=a.revision, ttl_ms=a.ttl_ms, key=a.key)
        print(json.dumps(result, sort_keys=True), flush=True)
        return 0
    except (Rejected, sqlite3.Error, ValueError) as exc:
        print(json.dumps({"rejected": type(exc).__name__}), flush=True)
        return 3


if __name__ == "__main__":
    sys.exit(main())
