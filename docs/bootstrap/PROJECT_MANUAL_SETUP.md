# GitHub Project Configuration

## Project

The owner-level private project [SIH26168 Development Roadmap](https://github.com/users/akhileshkancharla/projects/4) is linked exclusively to `akhileshkancharla/SIH26168-intelligent-dead-reckoning`.

Verified on `2026-09-03T21:21:51+05:30`:

- project number/ID: `4` / `PVT_kwHODQgbA84BiXCE`
- visibility: private
- linked repositories: one, the SIH26168 repository
- items: all 128 registered issues; no pull requests or draft items
- fields: 13 built-in plus 14 custom, 27 total
- views: all 14 required views
- populated deterministic values: 1,646

## Fields

| Field | Type |
|---|---|
| WP ID | Text |
| Parent WP | Text |
| Phase | Single select |
| Submission critical | Single select: Yes/No |
| Priority | Single select |
| Area | Single select |
| Owner role | Single select |
| Assignee | Built-in assignees |
| Start date | Date |
| Due date | Date |
| Estimated effort | Number |
| Evidence required | Single select: Yes/No |
| Scientific gate | Single select |
| Dependency status | Single select |
| Risk | Single select |
| Status | Built-in project status |

`Start date` and `Estimated effort` remain unset until an issue is actually scheduled. `Due date` uses the explicit issue-register date where present and otherwise derives from the issue's authoritative GitHub milestone.

## Views

The configured views are Submission Critical, Roadmap, Backlog, Ready, In Progress, In Review, Blocked, At Risk, By Owner, By Milestone, Scientific Gates, Operations Queue, Post-Submission, and Done.

Filters use repository labels as the source of truth. `By Owner` is grouped by Assignees, `By Milestone` is grouped by Milestone, and both Roadmap views use `Due date` as the target date.

## Reproducible synchronization

The synchronizer validates exact project membership before writing. It does not invent start dates or effort estimates.

```bash
node tools/bootstrap/configure_project.mjs --apply
node tools/bootstrap/configure_project.mjs --configure-views
node tools/bootstrap/configure_project.mjs --verify-values
```

The authenticated GitHub CLI token must include the `project` scope.
