"""Read-only, fail-closed GitHub Actions failure triage.

No platform/root-cause inference from absent steps alone. Never authorizes
merges, workflow reruns, payments, or changes to authoritative records.
"""
import json
import re
import sys

REQUIRED = frozenset(("unit-tests", "plugin-contract", "deployment-smoke"))
SHA = re.compile(r"[0-9a-f]{40}\Z")


class InvalidEvidence(ValueError):
    pass


def triage(run, jobs, checks):
    if type(run) is not dict or type(jobs) is not list or type(checks) is not list:
        raise InvalidEvidence("invalid evidence containers")
    sha = run.get("head_sha")
    if type(sha) is not str or not SHA.fullmatch(sha):
        raise InvalidEvidence("missing exact SHA")
    if run.get("status") != "completed" or run.get("event") not in ("push", "pull_request"):
        raise InvalidEvidence("not a completed supported run")
    if len(jobs) != 3 or len(checks) != 3:
        raise InvalidEvidence("expected exactly three jobs and check-runs")
    run_id, attempt = run.get("id"), run.get("run_attempt")
    if (type(run_id) is not int or run_id <= 0
            or type(attempt) is not int or attempt <= 0):
        raise InvalidEvidence("missing exact workflow run identity")
    runner_states = []
    by_name = {}
    by_id = {}
    for job in jobs:
        if type(job) is not dict or type(job.get("id")) is not int or type(job.get("name")) is not str:
            raise InvalidEvidence("invalid job")
        if job["name"] in by_name or job["id"] in by_id:
            raise InvalidEvidence("duplicate job")
        if (type(job.get("run_id")) is not int or job["run_id"] != run_id
                or type(job.get("run_attempt")) is not int
                or job["run_attempt"] != attempt or job.get("head_sha") != sha):
            raise InvalidEvidence("job belongs to another run, attempt or HEAD")
        if job.get("status") != "completed":
            raise InvalidEvidence("job status not completed")
        runner_id, runner_name = job.get("runner_id"), job.get("runner_name")
        if type(runner_id) is not int or runner_id < 0 or type(runner_name) is not str:
            raise InvalidEvidence("invalid runner identity metadata")
        if runner_id == 0 and runner_name == "":
            runner_states.append("ZERO_ID_EMPTY_NAME")
        elif runner_id > 0 and runner_name:
            runner_states.append("POSITIVE_ID_NAMED")
        else:
            raise InvalidEvidence("contradictory runner identity metadata")
        by_name[job["name"]] = job
        by_id[job["id"]] = job
    if set(by_name) != REQUIRED:
        raise InvalidEvidence("missing or unexpected required jobs")
    observed_annotations = {}
    for check in checks:
        if type(check) is not dict or type(check.get("id")) is not int or check["id"] not in by_id:
            raise InvalidEvidence("unmatched check-run")
        job = by_id[check["id"]]
        if check.get("status") != "completed":
            raise InvalidEvidence("check-run status not completed")
        if check.get("name") != job["name"] or check.get("conclusion") != job.get("conclusion"):
            raise InvalidEvidence("job/check-run disagreement")
        count = (check.get("output") or {}).get("annotations_count")
        if type(count) is not int or count < 0:
            raise InvalidEvidence("unknown annotation count")
        if check["id"] in observed_annotations:
            raise InvalidEvidence("duplicate check-run")
        observed_annotations[check["id"]] = count
    conclusions = [by_name[name]["conclusion"] for name in sorted(REQUIRED)]
    runner_assignment = ("ALL_ZERO_ID_EMPTY_NAME" if all(
        state == "ZERO_ID_EMPTY_NAME" for state in runner_states
    ) else "ALL_POSITIVE_ID_NAMED" if all(
        state == "POSITIVE_ID_NAMED" for state in runner_states
    ) else "MIXED_RUNNER_METADATA")
    if all(c == "success" for c in conclusions) and all(
        type(job.get("steps")) is list and len(job["steps"]) > 0 for job in jobs
    ) and run.get("conclusion") == "success":
        classification = "EXACT_RUN_JOBS_SUCCESS_STEPS_PRESENT"
    elif all(c == "failure" for c in conclusions) and all(
        job.get("steps") is None or job.get("steps") == [] for job in jobs
    ) and run.get("conclusion") == "failure":
        classification = ("ALL_JOBS_FAILED_NO_STEPS_RUNNER_ID_ZERO"
                          if runner_assignment == "ALL_ZERO_ID_EMPTY_NAME"
                          else "ALL_JOBS_FAILED_NO_STEPS_OBSERVED")
    else:
        classification = "INCONCLUSIVE_FAIL_CLOSED"
    return {
        "classification": classification,
        "head_sha": sha,
        "run_id": run_id,
        "run_attempt": attempt,
        "runner_assignment_metadata": runner_assignment,
        "annotation_counts": {name: observed_annotations[job["id"]] for name, job in sorted(by_name.items())},
        "root_cause": "NOT_PROVEN",
        "runner_or_billing_failure": "NOT_PROVEN",
        "runner_not_assigned": "NOT_PROVEN",
        "annotations_content": "NOT_READ",
        "safe_to_merge": False,
        "next_evidence": "Read check-run annotation messages or GitHub Actions UI before assigning cause",
    }


def main():
    try:
        evidence = json.load(sys.stdin)
        result = triage(evidence["run"], evidence["jobs"], evidence["checks"])
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        print("CI_TRIAGE_REJECTED: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
