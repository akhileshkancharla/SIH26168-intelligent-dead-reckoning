#!/usr/bin/env python3
"""Idempotently configure GitHub metadata for the SIH26168 repository.

Requires an already-authenticated GitHub CLI session. The script never reads,
prints, or persists credentials.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "akhileshkancharla/SIH26168-intelligent-dead-reckoning"
OWNER = "akhileshkancharla"
COLLABORATORS = [
    "FaisalTabrez",
    "Zeeshan1786",
    "likhithayepalagunta-19",
    "eragarg",
    "mjunaidqureshimct255a1405-art",
]


def api(endpoint: str, method: str = "GET", data: dict | None = None, check: bool = True):
    command = ["gh", "api", endpoint]
    if method != "GET":
        command += ["--method", method]
    encoded = None
    if data is not None:
        command += ["--input", "-"]
        encoded = json.dumps(data, ensure_ascii=False)
    result = subprocess.run(command, input=encoded, text=True, encoding="utf-8", capture_output=True)
    if check and result.returncode:
        raise RuntimeError(f"gh api {method} {endpoint} failed: {result.stderr.strip()}")
    if result.returncode:
        return None
    return json.loads(result.stdout) if result.stdout.strip() else {}


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def all_pages(endpoint: str) -> list[dict]:
    records = []
    page = 1
    separator = "&" if "?" in endpoint else "?"
    while True:
        batch = api(f"{endpoint}{separator}per_page=100&page={page}")
        records.extend(batch)
        if len(batch) < 100:
            return records
        page += 1


def configure_repository() -> dict:
    repo = api(f"repos/{REPOSITORY}", "PATCH", {
        "name": "SIH26168-intelligent-dead-reckoning",
        "private": True,
        "has_issues": True,
        "has_projects": True,
        "has_wiki": False,
        "allow_squash_merge": True,
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "allow_auto_merge": False,
        "delete_branch_on_merge": True,
        "default_branch": "main",
        "description": "Private SIH26168 development monorepo; evidence-bounded intelligent dead-reckoning submission",
    })
    return {"url": repo["html_url"], "visibility": repo["visibility"], "default_branch": repo["default_branch"]}


def configure_labels() -> dict[str, dict]:
    rows, _ = read_csv(ROOT / "docs/bootstrap/LABEL_REGISTER.csv")
    required = {row["Label"]: row for row in rows}
    current = {record["name"]: record for record in all_pages(f"repos/{REPOSITORY}/labels")}
    for name in sorted(set(current) - set(required)):
        api(f"repos/{REPOSITORY}/labels/{name}", "DELETE")
    for name, row in required.items():
        payload = {"name": name, "color": row["Color"], "description": row["Description"][:100]}
        if name in current:
            api(f"repos/{REPOSITORY}/labels/{name}", "PATCH", payload)
        else:
            api(f"repos/{REPOSITORY}/labels", "POST", payload)
    return {record["name"]: record for record in all_pages(f"repos/{REPOSITORY}/labels")}


def configure_milestones() -> dict[str, dict]:
    path = ROOT / "docs/bootstrap/MILESTONE_REGISTER.csv"
    rows, fields = read_csv(path)
    current = {record["title"]: record for record in all_pages(f"repos/{REPOSITORY}/milestones?state=all")}
    for row in rows:
        payload = {"title": row["Milestone"], "state": "open", "description": row["Purpose"], "due_on": row["Due UTC"]}
        if row["Milestone"] in current:
            record = api(f"repos/{REPOSITORY}/milestones/{current[row['Milestone']]['number']}", "PATCH", payload)
        else:
            record = api(f"repos/{REPOSITORY}/milestones", "POST", payload)
        row["Number"] = str(record["number"])
        row["URL"] = record["html_url"]
    write_csv(path, rows, fields)
    return {row["Milestone"]: row for row in rows}


def invite_collaborators() -> dict[str, str]:
    result = {}
    for username in COLLABORATORS:
        response = api(f"repos/{REPOSITORY}/collaborators/{username}", "PUT", {"permission": "push"})
        result[username] = "pending" if response and response.get("id") else "active-or-already-invited"
    invitations = all_pages(f"repos/{REPOSITORY}/invitations")
    pending = {item["invitee"]["login"].lower() for item in invitations}
    for username in COLLABORATORS:
        permission = api(f"repos/{REPOSITORY}/collaborators/{username}/permission", check=False)
        if permission and permission.get("permission") in {"read", "triage", "write", "maintain", "admin"}:
            result[username] = f"active:{permission['permission']}"
        elif username.lower() in pending:
            result[username] = "pending"
    return result


def slug_for(issue_id: str, title: str) -> str:
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-").split("-")[:5]
    return f"issue/{issue_id}-{'-'.join(words)}"


def common_labels(row: dict[str, str]) -> list[str]:
    wp = row["WP ID"][:5]
    labels = [
        f"wp:{wp[-2:]}", f"area:{row['Area']}", f"priority:{row['Priority']}",
        row["Status"], "evidence-required",
        "submission-critical" if row["Submission-critical flag"] == "yes" else "post-submission",
    ]
    if "." not in row["WP ID"]:
        labels.append("type:governance" if wp == "WP-00" else "type:feature")
    elif row["Owner role"] == "OPS-1":
        labels += ["type:operations", "role:operations", "beginner-safe"]
    elif row["Area"] in {"docs", "governance"}:
        labels.append("type:documentation")
    elif row["Area"] in {"ml", "data"}:
        labels.append("type:experiment")
    else:
        labels.append("type:feature")
    if row["Area"] in {"core", "analyzer", "contracts"}:
        labels.append("scientific-review")
    if row["Area"] in {"governance", "ci"}:
        labels.append("security-review")
    return sorted(set(labels))


def parent_body(row: dict[str, str], children: list[dict[str, str]]) -> str:
    child_lines = [f"- [ ] #{child['Issue number']} {child['Title']}" if child["Issue number"] else f"- [ ] {child['Title']}" for child in children]
    return f"""## Purpose
Deliver the bounded work-package outcome described by Architecture Revision 3: **{row['Title']}**.

## Components
See the immutable Revision 3 component register and this work package's linked child scopes.

## Interfaces
Only I-01 through I-22 contracts approved through WP-01 may be used; no bootstrap redesign is authorized.

## Dependencies
{row['Dependencies']}

## Linked child checklist
{chr(10).join(child_lines)}

## Acceptance boundary
Completion means every mandatory child, dependency, review, and evidence item is complete. A submission demonstration does not prove an unfinished scientific gate.

## Evidence
Evidence: https://github.com/{REPOSITORY}/actions
Required PR: none
Required review: pending

## Risks
Refer to `docs/architecture/SIH26168_Risk_Register_v1.csv`; escalate any safety, privacy, schedule, or scientific-integrity conflict.

## Exclusions
No fabricated evidence, unapproved architecture, private data in Git/CI, or implementation outside this work package.

## Owner
{row['Owner role']} — intended assignee `@{row['Intended assignee']}`

## Reviewer
`@{row['Reviewer']}`

## Milestone
{row['Milestone']}

## Definition of done
- [ ] Every mandatory child is closed through the authorized close workflow
- [ ] Dependencies are satisfied
- [ ] Evidence and required reviews are linked
- [ ] No blocked label remains
- [ ] `/approve-close` is current and closure is performed by an authorized closer
"""


def child_body(row: dict[str, str], parent_number: str) -> str:
    issue_id = row["WP ID"]
    operational = row["Owner role"] == "OPS-1"
    operations = """
## Frozen commands for OPS-1
1. `git fetch origin`
2. `git switch -c {branch}`
3. `python ci/verify_repository.py forbidden`
4. Run only the task-specific protocol commands added and approved by Akhilesh in this issue before Ready.
5. `python ci/verify_repository.py forbidden`
6. `git status --short`

Expected output: both policy scans print `PASS: forbidden`; task-specific output is preserved verbatim in the evidence record.

Prohibited actions: changing architecture, contracts, CODEOWNERS, CI design, thresholds, secrets, signing material, or scientific interpretation.

Immediate stop: task-specific protocol commands are absent/unapproved, private destination is unclear, output differs from the protocol, or any safety/privacy condition is uncertain. Report unchanged to Akhilesh and Faisal.
""" if operational else ""
    branch = slug_for(issue_id, row["Title"])
    return f"""## Scope
Execute only **{row['Title']}** as bounded by Architecture Revision 3.

## Non-scope
No adjacent WP implementation, architecture redesign, fake result, private-data commit, or scientific gate claim.

## Assignee
Intended: `@{row['Intended assignee']}`. Actual assignment is recorded only after GitHub confirms access.

## Support
Owner role `{row['Owner role']}`; escalate to `@akhileshkancharla` and `@FaisalTabrez`.

## Parent
Relates to #{parent_number}.

## Dependencies
{row['Dependencies']}. Keep this issue in Backlog/Blocked until dependencies are real.

## Expected files
Only files directly named by the accepted implementation plan; update this section before moving to Ready when paths are not yet frozen.

## Steps
1. Confirm dependencies and acceptance boundary.
2. Create the bounded branch.
3. Implement or execute only the stated scope.
4. Run applicable tests and repository-policy scans.
5. Open a draft PR within 24 hours of starting code.
6. Attach immutable evidence and request the named review.

## Acceptance criteria
- [ ] Scope output exists and is reviewable
- [ ] Applicable tests pass, or an unchanged failure report is attached
- [ ] Evidence identifies inputs, command/version, output, and limitations
- [ ] Private/prohibited-file scan passes
- [ ] Scientific status remains evidence-bounded

## Tests
Run the narrow component tests plus `python ci/verify_repository.py all` where supported. A missing tool is reported, never converted into a pass.

## Evidence
Evidence: https://github.com/{REPOSITORY}/actions
Required PR: pending
Required review: pending

## Estimate
One bounded child issue; refine before Ready without expanding scope.

## Due date
{row['Due date'] or 'Per milestone; post-submission unless explicitly promoted'}

## Reviewer
`@{row['Reviewer']}`

## Stop/escalate conditions
Stop on ambiguous architecture, missing private workspace, safety risk, unapproved threshold, dependency failure, secret exposure, or evidence-integrity failure.

## Branch name
`{branch}`

## Expected PR
One squash-merge PR using `Relates to #{parent_number}`; automatic close keywords are prohibited.
{operations.format(branch=branch)}"""


def can_assign(username: str, invitation_state: dict[str, str]) -> bool:
    return username.lower() == OWNER.lower() or invitation_state.get(username, "").startswith("active:")


def configure_issues(milestones: dict[str, dict], invitations: dict[str, str]) -> tuple[list[dict[str, str]], dict[str, dict]]:
    path = ROOT / "docs/bootstrap/ISSUE_REGISTER.csv"
    rows, fields = read_csv(path)
    existing = {item["title"]: item for item in all_pages(f"repos/{REPOSITORY}/issues?state=all") if "pull_request" not in item}
    milestone_numbers = {title: int(row["Number"]) for title, row in milestones.items()}
    by_wp = {row["WP ID"]: row for row in rows}

    # Create parents first so every child can reference a real parent issue number.
    ordered = [row for row in rows if "." not in row["WP ID"]] + [row for row in rows if "." in row["WP ID"]]
    for row in ordered:
        parent = row["WP ID"][:5]
        if "." in row["WP ID"]:
            body = child_body(row, by_wp[parent].get("Issue number", "TBD"))
        else:
            body = parent_body(row, [])
        payload = {
            "title": row["Title"], "body": body, "labels": common_labels(row),
            "milestone": milestone_numbers[row["Milestone"]],
        }
        if can_assign(row["Intended assignee"], invitations):
            payload["assignees"] = [row["Intended assignee"]]
        if row["Title"] in existing:
            record = api(f"repos/{REPOSITORY}/issues/{existing[row['Title']]['number']}", "PATCH", payload)
        else:
            record = api(f"repos/{REPOSITORY}/issues", "POST", payload)
        row["Issue number"] = str(record["number"])
        row["URL"] = record["html_url"]
        row["Actual assignee"] = ";".join(item["login"] for item in record.get("assignees", []))

    # Replace parent placeholders with the actual linked child checklist.
    for row in rows:
        if "." in row["WP ID"]:
            continue
        children = [child for child in rows if child["Parent"] == row["WP ID"]]
        api(f"repos/{REPOSITORY}/issues/{row['Issue number']}", "PATCH", {"body": parent_body(row, children)})

    write_csv(path, rows, fields)
    refreshed = {item["title"]: item for item in all_pages(f"repos/{REPOSITORY}/issues?state=all") if "pull_request" not in item}
    return rows, refreshed


def update_assignment_register(invitations: dict[str, str], issues: list[dict[str, str]]) -> None:
    path = ROOT / "docs/bootstrap/TEAM_ASSIGNMENT_MATRIX.csv"
    rows, fields = read_csv(path)
    for row in rows:
        username = row["Intended assignee"]
        actual = sorted({issue["Actual assignee"] for issue in issues if issue["WP ID"].startswith(row["WP"]) and issue["Actual assignee"]})
        row["Actual assignee"] = ";".join(actual) if actual else invitations.get(username, "pending invitation/verification")
    write_csv(path, rows, fields)


def main() -> None:
    authenticated = subprocess.run(["gh", "api", "user", "--jq", ".login"], text=True, encoding="utf-8", capture_output=True, check=True).stdout.strip()
    if authenticated.lower() != OWNER.lower():
        raise SystemExit(f"Authenticated owner mismatch: {authenticated}")
    repository = configure_repository()
    labels = configure_labels()
    milestones = configure_milestones()
    invitations = invite_collaborators()
    issues, remote_issues = configure_issues(milestones, invitations)
    update_assignment_register(invitations, issues)
    parents = sum("." not in row["WP ID"] for row in issues)
    children = sum("." in row["WP ID"] for row in issues)
    critical = sum(row["Submission-critical flag"] == "yes" for row in issues)
    if (parents, children, len(remote_issues), critical) != (18, 110, 128, 40):
        raise SystemExit(f"Remote count invariant failed: parents={parents}, children={children}, remote={len(remote_issues)}, critical={critical}")
    state = {
        "repository": repository,
        "authenticated_owner": authenticated,
        "label_count": len(labels),
        "milestone_count": len(milestones),
        "parent_issue_count": parents,
        "child_issue_count": children,
        "total_issue_count": len(remote_issues),
        "submission_critical_issue_count": critical,
        "collaborators": invitations,
    }
    (ROOT / "docs/bootstrap/GITHUB_CONFIGURATION_STATE.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"BOOTSTRAP ERROR: {exc}", file=sys.stderr)
        raise
