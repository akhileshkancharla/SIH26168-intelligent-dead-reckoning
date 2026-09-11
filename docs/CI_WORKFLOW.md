# Selective CI on the Windows runner

The maintained build/test entry point is `.github/workflows/ci.yml`. It replaces
17 standalone build/policy workflows. Six issue/review governance workflows keep
their existing events and review requirements.

## Events and execution

- Every PR update starts one CI run, with no workflow-level path filters.
- Pushes to `main` and manual dispatch run the full public/synthetic suite.
- Feature branch pushes do not create a duplicate CI run. Open a PR or dispatch
  manually to test a branch remotely.
- Concurrency cancels older runs for the same workflow, event and ref. Different
  PRs remain independent; one registered runner still executes one job at a time.
- Existing fork rejection remains in place before checkout in the selector and
  final gate. Other jobs depend on successful selection. Trusted repository
  branches and workflow changes require the existing owner review process.

There are seven jobs: `changes`, `policy`, `dataset`, `python`, `cpp`, `android`,
and `ci-required`. A documentation PR uses three runner jobs; a dataset PR uses
four. Governance jobs are additional. Unaffected test jobs are skipped before
runner allocation. Counts describe scheduling, not measured speedup.

## Conservative selection

`ci/select_checks.py` compares the pinned synthetic PR merge commit against its
base parent, covering the complete PR rather than just the last commit. Checkout
uses the event SHA and depth two. Both merge parents must match the event's base
and head identities. Missing history, unexpected parents or unavailable identity
select the full suite. Every job tests the same event SHA.

Git diff uses NUL-delimited paths and disables rename detection so both sides of
a rename participate. There is no API file-count truncation. Empty diffs also run
the full suite. Any selected job failure remains a failure.

| Changed input | Additional groups beyond policy |
| --- | --- |
| Ordinary documentation Markdown or root README/contribution/security/code-of-conduct text | None |
| Sanitized graph snapshot or bootstrap repository manifest | None; always validated by policy |
| Dataset tools/tests | Dataset |
| Bootstrap/acquisition Python tools/tests | Python |
| Android source/resources/manifest/Gradle/JNI | Android, C++, Python |
| Native core/includes/tests or root CMake | C++, Android, Python |
| Architecture, shared contracts/schemas/fixtures/bindings, package metadata, repository generator, CI, or any unclassified input | Full suite |

The broad Android/native selection accounts for JNI, generated bindings and
cross-language consumers that static extraction can miss. New modules default to
full validation until their actual dependencies and tests are reviewed. C-07
state ownership and I-01 through I-22 contracts are unchanged.

The always-running policy group tests CI selection/gating, Graphify sanitization,
generated binding drift and the governance model, then runs every existing
repository policy, including manifest and sanitized snapshot validation. The full
runner preflight runs in the Android group after pinned Java/Gradle setup; CMake
configuration checks the native toolchain when native tests are selected.

Python groups use unique temporary environments outside the repository, install
the project and its declared dependencies afresh, and clean up on normal exit or
test failure. Pip can reuse its download cache. Android runs JVM tests, lint and
the debug build in one Gradle invocation with the build cache and `--continue`;
failures still produce a nonzero exit code. Hard cancellation can leave temporary
files outside the checkout; environments are never reused as successful evidence.

## Required gate and rollout

The desired required checks are:

- `ci-required`
- `pull-request-governance-check`
- `sensitive-review-check`

`ci-required` uses `always()` and explicitly validates selector outputs and job
results. Policy and selection must succeed. Every selected group must succeed;
an unaffected group may be skipped. Missing outputs, cancellation and failed
dependencies cannot turn into a passing gate. No synthetic status is posted for
tests that were not run.

Roll out through a trusted repository branch and PR:

1. Push the CI change and let Selective CI finish. CI configuration changes select
   all groups. Obtain the normal current-head approvals.
2. Existing required check names may show as pending because their workflows
   were consolidated. Keep protection enabled. An administrator previews the
   targeted migration using the successful Selective CI run ID and PR number:

   ```powershell
   python ci/migrate_required_checks.py --pr PR_NUMBER --run-id RUN_ID
   ```

3. Review the displayed before/after check list, then run the same command with
   `--apply`. It requires a successful gate on the PR's current head, preserves
   unrelated required checks and their GitHub App restrictions, and modifies
   only status-check protection. Review counts, CODEOWNER rules, admin enforcement
   and other branch protections are not patched. It re-reads and verifies the
   result. Authentication needs repository administration access. Ruleset-based
   protection must be migrated separately by its administrator.
4. Merge normally after all requirements pass. Confirm the full `main` run.
   Rebase/update other open PRs to include the new workflow, so they can report
   `ci-required` too.

The workflow register describes this desired state; editing it does not change
GitHub settings. Do not run `tools/bootstrap/configure_branch_protection.py` for
this migration: it is an initial-bootstrap tool that replaces broader settings.
The historical repository generator refuses to overwrite a selective-CI checkout.

## Local checks and reruns

```powershell
python ci/select_checks.py --paths tools/dataset/manifest.py docs/CI_WORKFLOW.md
python -m unittest discover -s ci/tests -v
python ci/run_python_checks.py dataset
python ci/run_python_checks.py python
python ci/verify_repository.py all
```

After fixing a runner/environment problem without changing code:

```powershell
gh run rerun RUN_ID --failed -R akhileshkancharla/SIH26168-intelligent-dead-reckoning
```

GitHub reruns failed jobs and their dependent gate using the original run's code.
Push code fixes as a new commit. Manual full validation is available once the
workflow exists on the default branch:

```powershell
gh workflow run ci.yml --ref BRANCH -R akhileshkancharla/SIH26168-intelligent-dead-reckoning
```

If a grouping regression is found, retain `ci-required` and temporarily select
every group while fixing the selector; do not bypass protection. Private data,
physical-device jobs and scientific validation remain outside this CI suite.

GitHub behavior references: [required checks and skipped jobs](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks),
[rerunning jobs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs),
and [status-check protection API](https://docs.github.com/en/rest/branches/branch-protection#update-status-check-protection).
