"""Real subprocess / SQLite crash experiment, not distributed-worker E2E."""
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = "scripts.sqlite_lease_worker"


class SeparateProcessCrashRecovery(unittest.TestCase):
    def test_two_process_race_kill_and_fenced_recovery(self):
        with tempfile.TemporaryDirectory(prefix="project002-synthetic-") as tmp:
            db = str(Path(tmp) / "isolated.db")

            def args(operation, *extra):
                return [sys.executable, "-m", MODULE, operation, db, *extra]

            def invoke(operation, *extra, expected=0):
                proc = subprocess.run(args(operation, *extra), cwd=ROOT,
                                      capture_output=True, text=True, timeout=10)
                self.assertEqual(proc.returncode, expected, (proc.stdout, proc.stderr))
                return json.loads(proc.stdout)

            invoke("init")
            # Two separate OS processes attempt to claim the same durable lease.
            a = subprocess.Popen(args("acquire", "--owner", "worker-A",
                                      "--ttl-ms", "2200"), cwd=ROOT,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            b = subprocess.Popen(args("acquire", "--owner", "worker-B",
                                      "--ttl-ms", "2200"), cwd=ROOT,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            results = []
            for proc in (a, b):
                out, err = proc.communicate(timeout=10)
                self.assertIn(proc.returncode, (0, 3), (out, err))
                results.append((proc.returncode, json.loads(out)))
            self.assertEqual(sorted(rc for rc, _ in results), [0, 3])
            winner = next(data for rc, data in results if rc == 0)
            loser = "worker-B" if winner["owner"] == "worker-A" else "worker-A"
            self.assertEqual(winner["token"], 1)
            self.assertEqual(winner["revision"], 1)

            committed = invoke("write", "--owner", winner["owner"], "--token", "1",
                               "--revision", "1", "--key", "committed")
            self.assertEqual(committed["revision"], 2)
            self.assertEqual(committed["records"], {"committed": winner["owner"]})

            # OS process terminates without rollback/commit after changing a row.
            killed = subprocess.run(
                args("crash", "--owner", winner["owner"], "--token", "1",
                     "--revision", "2", "--key", "uncommitted"),
                cwd=ROOT, capture_output=True, text=True, timeout=10)
            self.assertEqual(killed.returncode, 71, killed.stderr)
            after_crash = invoke("inspect")
            self.assertEqual(after_crash["revision"], 2)
            self.assertEqual(after_crash["records"], {"committed": winner["owner"]})

            # Actual elapsed wall time, not a simulated clock.
            remaining = max(0.0, (after_crash["expires_ns"] - time.time_ns())
                            / 1_000_000_000 + 0.06)
            self.assertLess(remaining, 3.5)
            time.sleep(remaining)
            takeover = invoke("acquire", "--owner", loser, "--ttl-ms", "2200")
            self.assertEqual(takeover["token"], 2)
            self.assertEqual(takeover["revision"], 3)

            # Old owner refreshes the latest revision but cannot reuse token 1.
            rejected = invoke("write", "--owner", winner["owner"], "--token", "1",
                              "--revision", "3", "--key", "stale", expected=3)
            self.assertEqual(rejected["rejected"], "Rejected")
            recovered = invoke("write", "--owner", loser, "--token", "2",
                               "--revision", "3", "--key", "recovered")
            self.assertEqual(recovered["revision"], 4)
            self.assertEqual(recovered["records"], {
                "committed": winner["owner"], "recovered": loser,
            })
            self.assertEqual(invoke("inspect")["records"], recovered["records"])


if __name__ == "__main__":
    unittest.main()
