#!/usr/bin/env python3
"""Apply and verify strict protection for the main branch.

Run only after every listed status-check context has completed successfully at
least once. The configuration intentionally has no bypass actors.
"""

from __future__ import annotations

import json
import subprocess


REPOSITORY = "akhileshkancharla/SIH26168-intelligent-dead-reckoning"
REQUIRED_CHECKS = [
    "ci-required",
    "pull-request-governance-check",
    "sensitive-review-check",
]


def api(endpoint: str, method: str = "GET", data: dict | None = None):
    command = ["gh", "api", endpoint]
    if method != "GET":
        command += ["--method", method]
    encoded = None
    if data is not None:
        command += ["--input", "-"]
        encoded = json.dumps(data)
    result = subprocess.run(command, input=encoded, text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        raise SystemExit(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}


payload = {
    "required_status_checks": {"strict": True, "contexts": REQUIRED_CHECKS},
    "enforce_admins": True,
    "required_pull_request_reviews": {
        "dismiss_stale_reviews": True,
        "require_code_owner_reviews": True,
        "required_approving_review_count": 2,
        "require_last_push_approval": True,
    },
    "restrictions": None,
    "required_linear_history": True,
    "allow_force_pushes": False,
    "allow_deletions": False,
    "block_creations": False,
    "required_conversation_resolution": True,
    "lock_branch": False,
    "allow_fork_syncing": False,
}

api(f"repos/{REPOSITORY}/branches/main/protection", "PUT", payload)
state = api(f"repos/{REPOSITORY}/branches/main/protection")
observed = sorted(item["context"] for item in state["required_status_checks"]["checks"])
assert observed == sorted(REQUIRED_CHECKS), (observed, REQUIRED_CHECKS)
assert state["enforce_admins"]["enabled"] is True
assert state["required_pull_request_reviews"]["required_approving_review_count"] == 2
assert state["required_pull_request_reviews"]["require_code_owner_reviews"] is True
assert state["required_pull_request_reviews"]["dismiss_stale_reviews"] is True
assert state["required_pull_request_reviews"]["require_last_push_approval"] is True
assert state["required_linear_history"]["enabled"] is True
assert state["allow_force_pushes"]["enabled"] is False
assert state["allow_deletions"]["enabled"] is False
assert state["required_conversation_resolution"]["enabled"] is True
print(json.dumps({
    "branch": "main",
    "required_checks": observed,
    "approvals": 2,
    "code_owner_review": True,
    "dismiss_stale_reviews": True,
    "last_push_approval": True,
    "admin_enforcement": True,
    "linear_history": True,
    "force_pushes": False,
    "deletions": False,
    "conversation_resolution": True,
}, indent=2))
