"""Independent read-only GitHub Actions postmerge CI readback for public synthetic repo.

Not a scheduler attestation, independent AI cold start, durable lease, or production approval.
Runs only after synthetic-ci push workflow completes; all API reads are GitHub-origin.
"""
import json
import os
import re
import sys
from urllib.request import Request, urlopen

REPO = "THECHANJONG/project002-synthetic-pr-sandbox"
WORKFLOW = "synthetic-ci.yml"
REQUIRED = {"unit-tests", "plugin-contract", "deployment-smoke"}
SHA = re.compile(r"[0-9a-f]{40}\Z")


class UnverifiedPostmerge(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise UnverifiedPostmerge(message)


def verify(run, jobs, branch, *, run_id, expected_sha):
    """Verify exact event SHA, full job set, run attempt and latest remote main."""
    require(type(run_id) is int and run_id > 0, "invalid run id")
    require(type(expected_sha) is str and SHA.fullmatch(expected_sha), "invalid expected SHA")
    require(type(run) is dict and type(jobs) is list and type(branch) is dict,
            "missing external evidence")
    repo = run.get("repository")
    require(type(repo) is dict and repo.get("full_name") == REPO,
            "wrong run repository")
    require(run.get("id") == run_id and type(run.get("id")) is int,
            "wrong run identity")
    attempt = run.get("run_attempt")
    require(type(attempt) is int and attempt > 0, "invalid run attempt")
    require(run.get("path") == ".github/workflows/" + WORKFLOW,
            "wrong workflow path")
    require(run.get("event") == "push" and run.get("head_branch") == "main"
            and run.get("head_sha") == expected_sha,
            "not an exact main push")
    require(run.get("status") == "completed" and run.get("conclusion") == "success",
            "run incomplete or unsuccessful")
    require(branch.get("name") == "main" and type(branch.get("commit")) is dict
            and branch["commit"].get("sha") == expected_sha,
            "latest main differs from completed run")
    require(len(jobs) == len(REQUIRED), "job inventory incomplete or unexpected")
    seen = set()
    for job in jobs:
        require(type(job) is dict and type(job.get("name")) is str, "invalid job")
        name = job["name"]
        require(name in REQUIRED and name not in seen, "duplicate/unexpected job")
        seen.add(name)
        require(job.get("run_id") == run_id and type(job.get("run_id")) is int
                and job.get("run_attempt") == attempt
                and type(job.get("run_attempt")) is int,
                "job from different run/attempt")
        require(job.get("head_sha") == expected_sha
                and job.get("status") == "completed"
                and job.get("conclusion") == "success", "job failed or wrong HEAD")
    require(seen == REQUIRED, "missing required job")
    return {"result": "EXTERNAL_POSTMERGE_MAIN_CI_VERIFIED", "repository": REPO,
            "main_sha": expected_sha, "run_id": run_id, "run_attempt": attempt,
            "jobs": sorted(seen), "scheduler_invocation_attestation": "UNAVAILABLE",
            "independent_ai_cold_start": "NOT_PROVEN",
            "shared_remote_cas_lease_fencing": "NOT_PROVEN",
            "original_private_main_verified": False}


def fetch_json(path, token):
    url = "https://api.github.com/repos/" + REPO + "/" + path
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "project002-synthetic-readonly"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=15) as response:
        require(response.status == 200, "GitHub API not OK")
        return json.load(response)


def main():
    try:
        run_id_text = os.environ["SOURCE_RUN_ID"]
        require(re.fullmatch(r"[1-9][0-9]{0,19}", run_id_text) is not None,
                "invalid source run ID")
        run_id = int(run_id_text)
        sha = os.environ["EXPECTED_HEAD"]
        token = os.environ.get("GH_READ_TOKEN", "")
        run = fetch_json("actions/runs/" + str(run_id), token)
        jobs_data = fetch_json("actions/runs/" + str(run_id) + "/jobs?per_page=100", token)
        require(type(jobs_data) is dict and jobs_data.get("total_count") == 3,
                "job inventory not complete")
        branch = fetch_json("branches/main", token)
        result = verify(run, jobs_data.get("jobs"), branch, run_id=run_id,
                        expected_sha=sha)
    except (KeyError, ValueError, OSError, TypeError) as exc:
        print("POSTMERGE_READBACK_REJECTED: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
