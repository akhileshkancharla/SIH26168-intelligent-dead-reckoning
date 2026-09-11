#!/usr/bin/env python3
"""Preview (or apply) only the required-check migration after a green PR run."""
from __future__ import annotations

import argparse
import json
import subprocess

REPOSITORY = "akhileshkancharla/SIH26168-intelligent-dead-reckoning"
REPLACED = {
    "repository-policy-check", "forbidden-files-check", "secret-scanning-check",
    "markdown-check", "internal-links-check", "json-check", "csv-check",
    "contracts-check", "python-smoke-check", "cpp-smoke-check", "android-jvm-check",
    "android-lint-check", "android-debug-build-check", "manifest-check",
    "generated-file-drift-check", "graphify-snapshot-check", "dataset-check", "runner-preflight",
}
GOVERNANCE = ("pull-request-governance-check", "sensitive-review-check")


def api(endpoint: str, method: str = "GET", payload: dict | None = None):
    command = ["gh", "api", endpoint, "--method", method]
    if payload is not None:
        command += ["--input", "-"]
    result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise SystemExit(result.stderr.strip())
    return json.loads(result.stdout)


def replacement(current: dict, app_id: int) -> dict:
    if not isinstance(current.get("strict"), bool):
        raise ValueError("Existing required-status-check protection is unavailable")
    # Preserve unknown required checks and their provider restrictions verbatim.
    checks = [dict(item) for item in current.get("checks", [])]
    known = {item["context"] for item in checks}
    checks += [{"context": name, "app_id": -1} for name in current.get("contexts", []) if name not in known]
    checks = [{"context": item["context"], "app_id": item.get("app_id") or -1}
              for item in checks if item["context"] not in REPLACED | {"ci-required"}]
    for name in GOVERNANCE:
        if not any(item["context"] == name for item in checks):
            checks.append({"context": name, "app_id": app_id})
    checks.append({"context": "ci-required", "app_id": app_id})
    return {"strict": current["strict"], "checks": checks}


def verify_evidence(pr: dict, run: dict, jobs: dict, repository: str) -> dict:
    if (pr.get("state") != "open" or pr.get("base", {}).get("ref") != "main"
            or pr.get("head", {}).get("repo", {}).get("full_name") != repository):
        raise ValueError("Use an open, trusted repository PR targeting main")
    if (run.get("event") != "pull_request" or run.get("path") != ".github/workflows/ci.yml"
            or run.get("conclusion") != "success" or run.get("status") != "completed"
            or run.get("head_sha") != pr["head"]["sha"]
            or not any(item.get("number") == pr["number"] for item in run.get("pull_requests", []))):
        raise ValueError("The run must be successful Selective CI for this PR's current head")
    gates = [job for job in jobs.get("jobs", []) if job.get("name") == "ci-required"]
    if len(gates) != 1 or gates[0].get("conclusion") != "success":
        raise ValueError("Exactly one successful ci-required job is required")
    return gates[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=REPOSITORY)
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--apply", action="store_true", help="Apply the displayed status-check migration")
    args = parser.parse_args()
    prefix = f"repos/{args.repo}"
    pr = api(f"{prefix}/pulls/{args.pr}")
    run = api(f"{prefix}/actions/runs/{args.run_id}")
    jobs = api(f"{prefix}/actions/runs/{args.run_id}/jobs?filter=latest&per_page=100")
    gate = verify_evidence(pr, run, jobs, args.repo)
    check_id = gate["check_run_url"].rstrip("/").split("/")[-1]
    check = api(f"{prefix}/check-runs/{check_id}")
    if check.get("app", {}).get("slug") != "github-actions":
        raise ValueError("The gate must be produced by GitHub Actions")
    endpoint = f"{prefix}/branches/main/protection/required_status_checks"
    current = api(endpoint)
    payload = replacement(current, check["app"]["id"])
    print(json.dumps({"repository": args.repo, "branch": "main", "before": current, "after": payload}, indent=2))
    if args.apply:
        # Re-read immediately before mutation; refuse to overwrite a concurrent edit.
        if api(endpoint) != current or api(f"{prefix}/pulls/{args.pr}")["head"]["sha"] != pr["head"]["sha"]:
            raise ValueError("Protection or PR head changed; preview again")
        api(endpoint, "PATCH", payload)
        observed = api(endpoint)
        normalize = lambda items: sorted((item["context"], item.get("app_id") or -1) for item in items)
        if observed["strict"] != payload["strict"] or normalize(observed["checks"]) != normalize(payload["checks"]):
            raise ValueError("Required-check migration did not verify")
        print("Required checks updated and verified. Other protection fields were not modified.")
    else:
        print("Preview only. Add --apply after reviewing the migration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
