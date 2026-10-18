# Repository Agent Instructions

## Graphify knowledge-transfer workflow

1. Read `docs/architecture/START_HERE.md` before implementation changes.
2. Inspect the relevant Architecture Revision 3 components and I-01 through I-22 interfaces.
3. Inspect `docs/architecture/dependency-graph/GRAPH_REPORT.md` and the sanitized `graph.json` snapshot.
4. Query or traverse relevant upstream and downstream dependencies before editing an important module.
5. Inspect the actual source, tests, manifests, resources, and build configuration before drawing conclusions.
6. Never use Graphify alone as proof that code is unused.
7. Account for JNI symbols, Android callbacks and manifests, reflection, generated code, dependency injection, resources, and serialized contracts that static extraction can miss.
8. Regenerate the sanitized graph after meaningful architectural or multi-file changes. Isolated spelling or comment-only changes do not require regeneration.
9. Never commit raw `graphify-out/`; commit only the verified sanitized snapshot.
10. Architecture Revision 3 overrides generic Graphify inference.
11. S2 C-07 remains the sole owner of navigation state, operational biases, covariance, and evidence acceptance.
12. ML and map components produce bounded proposals and cannot directly overwrite the navigation core.

Before deleting code or performing a major refactor, combine graph traversal with text search, Android manifest and Gradle inspection, native/JNI symbol inspection, configuration and schema inspection, build/test evidence, and runtime-entry-point reasoning.

## Mandatory automated PR review handoff

This protocol applies to every current and future PR in this repository, including PRs #169, #170 and #191 through #198. It is mandatory agent workflow after creating a PR, rebasing/restacking/updating its branch, resolving reviewer change requests, or pushing any new commit to an open PR. Complete it in the active task; do not end after a push or PR creation without a posted GitHub handoff. No unattended background automation is required by this rule.

1. Inspect the PR's exact current head SHA, base branch/head, current remote ancestry, GitHub mergeability, review requests, review threads and current-head check results. Describe the actual operation (merge, rebase or restack) accurately. Never assert conflict-free lineage when it is conflicting or unknown; resolve authorized conflicts before reporting readiness, or state the blocker explicitly.
2. Automatically request current-head reviews from both `akhileshkancharla` and `FaisalTabrez` with `gh pr edit <number> --add-reviewer akhileshkancharla --add-reviewer FaisalTabrez`. An already outstanding request satisfies this step; inspect the resulting requests and retry a missing request if necessary. Preserve additional domain/CODEOWNER requests. Never self-approve, bypass review gates, or merge unless separately authorized.
3. Write a structured Markdown handoff to a temporary file outside the checkout and publish it with `gh pr comment <number> --body-file <file>`. Always tag `@akhileshkancharla` and `@FaisalTabrez`. Use the repository's Scope, Evidence, Review and Non-scope sections, `Relates to #...` parent/child issue references, concrete source/test changes and reviewer-finding resolutions, exact reviewed head and base lineage, remaining limitations and any stacked-parent merge dependency. Automatic issue-close keywords are prohibited.
4. Report exact, attributable verification outcomes for the final head: test names/tasks and actionable/executed/cached/up-to-date task counts where recorded; test totals/failures/errors/skips; Graphify version and node/edge/community counts; committed repository-manifest SHA-256; repository policy, contract-binding, secret/prohibited-artifact and diff checks. Link current-head CI evidence. Distinguish local verification, remote CI and historical results. Missing/unrecorded metrics are explicitly NOT RUN or NOT RECORDED, never invented. For unchanged artifacts in documentation-only PRs, report their committed identities as inherited/unchanged and explain why builds or graph regeneration were not applicable; do not present inherited results as new verification.
5. Keep queued, pending, cancelled, failed and unavailable checks explicit. Compiled instrumentation is not device-executed evidence; synthetic fixtures, UI tests, Graphify and desk rehearsals cannot establish physical/scientific gates. Request final approval/squash-merge only conditionally on all repository gates; a stacked child must follow its parent and be revalidated after any base/head change.
6. Verify that the comment was successfully posted and retain its URL. If publication or reviewer requests fail, retry a safe correction and report any remaining failure explicitly. The final response must link the posted handoff and identify pending approvals/checks or blockers. Never silently omit this step for an existing PR or a follow-up push.

If `gh` is not on PATH, use the installed GitHub CLI executable at its verified absolute location. Prepare exact multiline comment text in a body file; do not interpolate it into shell command strings. This workflow does not authorize unrelated messages, automatic merges, background schedules, fabricated evidence or changes outside the task's scope.
