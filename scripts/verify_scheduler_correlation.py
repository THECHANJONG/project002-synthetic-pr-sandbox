"""Read-only correlation of a platform automation run and GitHub PR/CI.

A PR body can repeat a platform run ID without proving the scheduler created it.
Even a passing correlation is CORRELATED_NOT_ATTESTED, never autonomous E2E.
All evidence must be independently fetched by the caller; this module cannot
authorize merging, change an authoritative pointer, or attest an AI cold start.
"""
from datetime import datetime, timezone
import re
import uuid

SHA = re.compile(r"[0-9a-f]{40}\Z")
REQUIRED = {"unit-tests", "plugin-contract", "deployment-smoke"}


class InvalidCorrelation(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise InvalidCorrelation(reason)


def _time(value):
    _require(type(value) is str and value.endswith("Z"), "non-UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InvalidCorrelation("invalid timestamp") from exc
    _require(parsed.utcoffset().total_seconds() == 0, "non-UTC timestamp")
    return parsed


def _sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def _check_run(run, *, sha, event, branch, pr_number=None):
    _require(type(run) is dict, "missing CI run")
    _require(run.get("head_sha") == sha and run.get("event") == event
             and run.get("head_branch") == branch, "wrong CI source")
    _require(run.get("status") == "completed" and run.get("conclusion") == "success",
             "CI not successful")
    _require(type(run.get("id")) is int and run["id"] > 0
             and type(run.get("run_attempt")) is int and run["run_attempt"] > 0,
             "invalid CI identity")
    if pr_number is not None:
        _require(type(run.get("pr_number")) is int and run["pr_number"] == pr_number,
                 "wrong PR binding")
    jobs = run.get("jobs")
    _require(type(jobs) is list and len(jobs) == 3, "incomplete CI jobs")
    names = set()
    for job in jobs:
        _require(type(job) is dict and type(job.get("name")) is str, "invalid CI job")
        _require(job["name"] not in names, "duplicate CI job")
        names.add(job["name"])
        _require(job.get("status") == "completed" and job.get("conclusion") == "success"
                 and job.get("head_sha") == sha
                 and type(job.get("run_id")) is int and job["run_id"] == run["id"]
                 and type(job.get("run_attempt")) is int
                 and job["run_attempt"] == run["run_attempt"], "mixed/failed CI job")
    _require(names == REQUIRED, "missing required CI job")
    return _time(run.get("completed_at"))


def correlate(platform, github):
    """Validate chronology and identities; return correlation, NOT provenance."""
    _require(type(platform) is dict and type(github) is dict, "missing evidence")
    run_id = platform.get("id")
    _require(type(run_id) is str, "missing platform run ID")
    try:
        _require(str(uuid.UUID(run_id)) == run_id, "noncanonical platform run ID")
    except ValueError as exc:
        raise InvalidCorrelation("invalid platform run ID") from exc
    _require(platform.get("recorded_status") == "completed", "platform run incomplete")
    scheduled = _time(platform.get("scheduled_for"))
    started = _time(platform.get("started_at"))
    finished = _time(platform.get("completed_at"))
    _require(scheduled <= started <= finished, "platform chronology invalid")

    pr = github.get("pr")
    _require(type(pr) is dict, "missing PR")
    head, merged_sha = pr.get("head_sha"), pr.get("merge_commit_sha")
    _require(_sha(head) and _sha(merged_sha), "invalid PR SHA")
    _require(type(pr.get("number")) is int and pr["number"] > 0
             and pr.get("merged") is True and pr.get("base_branch") == "main"
             and type(pr.get("head_branch")) is str and pr["head_branch"] != "main",
             "PR not verified merged")
    _require(github.get("automation_run_id") == run_id,
             "GitHub self-reported run ID mismatch")
    created, merged = _time(pr.get("created_at")), _time(pr.get("merged_at"))
    pr_ci = _check_run(github.get("pr_ci"), sha=head, event="pull_request",
                       branch=pr["head_branch"], pr_number=pr["number"])
    post_ci = _check_run(github.get("postmerge_ci"), sha=merged_sha,
                         event="push", branch="main")
    _require(github.get("main_readback_sha") == merged_sha,
             "postmerge main readback mismatch")
    _require(started <= created <= pr_ci <= merged <= post_ci <= finished,
             "cross-system chronology invalid")
    return {
        "correlation": "CORRELATED_NOT_ATTESTED",
        "scheduler_invocation_attestation": "UNAVAILABLE",
        "autonomous_development_e2e": "NOT_PROVEN",
        "platform_run_id": run_id,
        "pr_number": pr["number"],
        "pr_head_sha": head,
        "main_after_sha": merged_sha,
        "limits": ["GitHub run ID binding is self-reported, not platform-signed",
                   "timestamps and exact-head CI cannot prove independent AI execution"],
    }
