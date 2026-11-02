"""Read-only live GitHub Actions artifact provenance check for a synthetic candidate.

Checks the live run and artifact API records, downloaded ZIP digest, exact
checkout commit and the existing offline allowlist validator in ONE path.
Does not prove AI authoring, scheduler origin, independent workers or PR merge.
Never performs a GitHub write.
"""
import argparse
import hashlib
import io
import os
import json
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
import zipfile

from scripts.prepare_patch_artifact import PROJECT_REPO
from scripts.validate_patch_promotion import InvalidPromotion, validate_artifact

API = "https://api.github.com/repos/" + PROJECT_REPO
WORKFLOW = ".github/workflows/phase1-bounded-patch-probe.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _json_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise InvalidPromotion("duplicate API JSON key")
        obj[key] = value
    return obj


def _no_constant(value):
    raise InvalidPromotion("nonfinite API JSON number")


def _get_json(url):
    req = Request(url, headers={"Accept": "application/vnd.github+json",
                                "User-Agent": "project002-readonly-attestor"})
    with urlopen(req, timeout=20) as response:
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise InvalidPromotion("API response exceeds bound")
    return json.loads(data.decode("utf-8"), object_pairs_hook=_json_pairs,
                      parse_constant=_no_constant)


class _HTTPSOnlyRedirect(HTTPRedirectHandler):
    """Never downgrade artifact downloads to HTTP."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise InvalidPromotion("non-HTTPS artifact redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _artifact_request(url, token=None):
    """Token, if explicitly supplied, is sent to GitHub API only.

    add_unredirected_header prevents urllib from forwarding the bearer
    credential to GitHub's separate artifact CDN redirect host.
    """
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "api.github.com"
            or not url.startswith(API + "/actions/artifacts/")
            or not url.endswith("/zip")):
        raise InvalidPromotion("untrusted artifact API URL")
    req = Request(url, headers={"Accept": "application/vnd.github+json",
                                "User-Agent": "project002-readonly-attestor"})
    if token is not None:
        if (type(token) is not str or not token.strip()
                or any(c in token for c in "\r\n")):
            raise InvalidPromotion("invalid artifact token")
        req.add_unredirected_header("Authorization", "Bearer " + token)
    return req


def _get_zip(url, token=None):
    req = _artifact_request(url, token)
    with build_opener(_HTTPSOnlyRedirect()).open(req, timeout=30) as response:
        if urlsplit(response.geturl()).scheme != "https":
            raise InvalidPromotion("non-HTTPS artifact redirect")
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise InvalidPromotion("artifact ZIP exceeds bound")
    return data


def _checkout_head(root):
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, timeout=10, check=True)
    return result.stdout.strip()


def _read_zip(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            entries = z.infolist()
            if len(entries) != 2 or {x.filename for x in entries} != {
                    "receipt.json", "candidate.patch"}:
                raise InvalidPromotion("unexpected ZIP inventory")
            result = {}
            for entry in entries:
                if (entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16)
                        or entry.file_size > 8192
                        or entry.compress_size > 2_000_000):
                    raise InvalidPromotion("unsafe ZIP member")
                payload = z.read(entry)
                if len(payload) != entry.file_size:
                    raise InvalidPromotion("ZIP member size mismatch")
                result[entry.filename] = payload
            return result
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise InvalidPromotion("malformed artifact ZIP") from exc


def attest(run_id, artifact_id, *, expected_head, checkout_root,
           json_get=_get_json, zip_get=_get_zip, head_get=_checkout_head):
    """Verify live metadata + artifact + checkout without modifying the repo."""
    if (type(run_id) is not int or run_id <= 0
            or type(artifact_id) is not int or artifact_id <= 0
            or type(expected_head) is not str or not SHA.fullmatch(expected_head)):
        raise InvalidPromotion("invalid independently pinned identity")
    if head_get(checkout_root) != expected_head:
        raise InvalidPromotion("checkout is not exact run HEAD")
    try:
        run = json_get(API + "/actions/runs/" + str(run_id))
        if (type(run) is not dict or type(run.get("id")) is not int
                or run["id"] != run_id
                or run.get("repository", {}).get("full_name") != PROJECT_REPO
                or run.get("path") != WORKFLOW
                or run.get("event") != "push"
                or run.get("head_branch") != "main"
                or run.get("head_sha") != expected_head
                or run.get("status") != "completed"
                or run.get("conclusion") != "success"
                or type(run.get("run_attempt")) is not int
                or run["run_attempt"] <= 0):
            raise InvalidPromotion("live run identity or outcome mismatch")
        listing = json_get(API + "/actions/runs/" + str(run_id) + "/artifacts")
        artifacts = listing["artifacts"]
        if type(artifacts) is not list:
            raise InvalidPromotion("invalid artifact listing")
        matches = [x for x in artifacts if type(x) is dict
                   and type(x.get("id")) is int and x["id"] == artifact_id]
        if len(matches) != 1:
            raise InvalidPromotion("artifact missing or ambiguous")
        artifact = matches[0]
        expected_name = f"phase1-bounded-patch-{run_id}-{run['run_attempt']}"
        archive_url = API + "/actions/artifacts/" + str(artifact_id) + "/zip"
        workflow_run = artifact.get("workflow_run")
        digest = artifact.get("digest")
        if (artifact.get("name") != expected_name
                or artifact.get("expired") is not False
                or artifact.get("archive_download_url") != archive_url
                or type(digest) is not str or not DIGEST.fullmatch(digest)
                or type(workflow_run) is not dict
                or type(workflow_run.get("id")) is not int
                or workflow_run["id"] != run_id
                or workflow_run.get("head_sha") != expected_head
                or workflow_run.get("head_branch") != "main"):
            raise InvalidPromotion("live artifact provenance mismatch")
        archive = zip_get(archive_url)
        if hashlib.sha256(archive).hexdigest() != digest.removeprefix("sha256:"):
            raise InvalidPromotion("live archive digest mismatch")
        members = _read_zip(archive)
        receipt = json.loads(members["receipt.json"].decode("utf-8"),
                             object_pairs_hook=_json_pairs,
                             parse_constant=_no_constant)
        if receipt.get("event") != run["event"]:
            raise InvalidPromotion("receipt event disagrees with GitHub")
        with tempfile.TemporaryDirectory(prefix="phase1-live-verify-") as tmp:
            for name, data in members.items():
                (Path(tmp) / name).write_bytes(data)
            verdict = validate_artifact(
                tmp, expected_head=expected_head, expected_run_id=run_id,
                expected_attempt=run["run_attempt"], checkout_root=checkout_root)
        return {
            **verdict,
            "github_run_api_attestation": "VERIFIED_METADATA_AND_ARCHIVE",
            "artifact_id": artifact_id,
            "run_id": run_id,
            "exact_checkout_sha": expected_head,
            "scheduler_invocation_attestation": "UNAVAILABLE",
            "ai_authored_pr_merge": "NOT_PROVEN",
        }
    except (KeyError, TypeError, AttributeError, OSError, ValueError,
            subprocess.SubprocessError) as exc:
        if isinstance(exc, InvalidPromotion):
            raise
        raise InvalidPromotion("live provenance could not be verified") from exc


def main():
    parser = argparse.ArgumentParser(description="Read-only public Actions proof")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--use-actions-token", action="store_true",
                        help="Use existing GITHUB_TOKEN only after actions:read approval")
    args = parser.parse_args()
    if args.use_actions_token:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            parser.error("--use-actions-token requires GITHUB_TOKEN")
        zip_get = lambda url: _get_zip(url, token=token)
    else:
        zip_get = _get_zip
    print(json.dumps(attest(args.run_id, args.artifact_id,
                            expected_head=args.expected_head,
                            checkout_root=args.checkout,
                            zip_get=zip_get), sort_keys=True))


if __name__ == "__main__":
    main()
