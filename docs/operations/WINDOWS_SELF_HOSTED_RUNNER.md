# Windows self-hosted runner operations

## Purpose and routing

The repository uses one Windows x64 self-hosted GitHub Actions runner to preserve required CI and governance automation when GitHub-hosted Actions capacity is unavailable. Jobs target all four labels exactly:

```yaml
runs-on: [self-hosted, Windows, X64, sih26168]
```

All 22 repository workflows are routed to this label set. No workflow retains an automatic GitHub-hosted fallback. Existing workflow names and job/check names remain unchanged. The repository-policy workflow also contains an isolated `runner-preflight` job; it is an additional diagnostic check and does not replace `repository-policy-check`.

Checkout-based pull-request jobs fail before checkout when the pull request originates from a fork. A fork contributor must have a maintainer reproduce the commit on a reviewed branch in this repository. This keeps required checks fail-closed without executing fork-controlled code on the machine. Governance jobs that do not checkout repository content continue to evaluate pull-request or issue metadata.

## Availability limitation

This is a single-machine runner and does not provide continuous availability. Matching jobs remain queued when the computer is powered off, asleep, disconnected, or when the runner service is stopped. Queued work must never be reported as passed or executed.

In the repository **Settings > Actions > Runners** page, confirm that the runner shows all four expected labels and an `Idle` or `Active` status. `Idle` means it can accept work; `Active` means it is running a job. An offline status is a validation blocker.

## Required host prerequisites

The service account must be able to read and execute:

- Git and Windows PowerShell.
- CMake 3.20 or newer.
- A Visual Studio C++ toolchain, `clang-cl`, `clang++`, or `g++` capable of building the C++20 project.
- An Android SDK exposed through `ANDROID_SDK_ROOT` or `ANDROID_HOME`, including platform 35 and complete build tools.
- At least 5 GiB free on the workspace drive.
- Outbound HTTPS access required by GitHub Actions, the pinned setup actions, Maven Central, and Google's Android repositories.

Pinned setup actions select Python 3.12, Temurin Java 17, and Gradle 8.10.2 without administrator-level installation. The Android SDK, CMake, and C++ compiler are host prerequisites. Workflows must stop with the original failure if a prerequisite requires administrator-level installation; the machine owner performs that installation separately and reruns CI.

## Service-account implications

The runner service executes as `NT AUTHORITY\NETWORK SERVICE`, not as an interactive user. User-scoped PATH entries, Android SDK variables, package caches, mapped drives, certificates, and permissions may therefore be invisible to CI. Configure required environment variables and filesystem access at machine/service scope, then restart the runner service so it receives the updated environment.

The preflight intentionally reports only bounded tool versions, command visibility, the runner workspace repository location, Android component presence, disk capacity, and whether the expected service identity is in use. It does not enumerate environment variables, print tokens, or inspect unrelated directories.

## Toolchain verification

`ci/self_hosted_runner_preflight.ps1` runs after the repository's existing pinned setup actions. It fails when the expected Windows/X64 service context, Python 3.12, Java 17, Gradle 8.10.2, CMake, C++ compiler, Android SDK components, disk capacity, or workspace writability is unavailable.

For an interactive diagnostic from a clean checkout, run:

```powershell
powershell -NoProfile -File .\ci\self_hosted_runner_preflight.ps1
```

An interactive run can differ from the service result. CI output under the service account is authoritative for runner readiness. Never add credentials merely to make preflight pass.

## Safe startup and shutdown

Only the machine owner should control the Windows service, from an elevated PowerShell session. First verify in GitHub that no job is `Active` before stopping or restarting it.

```powershell
$runnerService = Get-Service -Name 'actions.runner.*'
$runnerService | Format-Table Name, Status
Start-Service -InputObject $runnerService
Stop-Service -InputObject $runnerService
Restart-Service -InputObject $runnerService
```

Do not suspend, shut down, update, or restart the computer while a job is Active. After startup, confirm the runner returns to `Idle` before relying on required checks.

## Workspace and cleanup policy

The GitHub runner workspace and tool caches are operational state, not evidence storage. Workflows may create normal build outputs only inside their assigned workspace. They must not access unrelated files or perform administrator-level cleanup.

- Never copy datasets, personal files, raw S1 sessions, private analyzer evidence, long-lived credentials, registration tokens, keystores, or signing keys into the workspace.
- Never commit `_work`, `_diag`, `.runner`, `.credentials`, `.credentials_rsaparams`, service configuration, build output, or tool caches.
- Let checkout and build tools clean their own bounded repository/build paths.
- Perform exceptional cleanup only while the service is stopped and no job is queued or Active. The machine owner must review exact targets and retain diagnostic logs needed for an incident before removing anything.

## Security limitations

A self-hosted runner is not an isolation boundary. Same-repository branches that CI executes can run with the service account's permissions and can persist files in writable host locations. Repository write access therefore implies the ability to propose code that may execute on this machine after push or pull-request events.

Mitigations in this repository include least-privilege workflow permissions, immutable action SHAs, no repository secrets, non-persistent checkout credentials, a fail-closed fork guard, no `pull_request_target` execution of PR-controlled code, and forbidden/private-file scanning. These controls do not make a single long-lived machine equivalent to an ephemeral hosted runner. Keep the service account unprivileged and the host free of unrelated private data.

## Temporarily disable the runner

Wait until no job is Active, stop the runner service, and verify the GitHub runner page shows it offline. Existing matching jobs will queue. Do not change workflow labels merely to bypass an outage, and do not claim queued jobs passed.

## Remove or re-register safely

Removal and rotation are machine-owner operations:

1. Stop new work and wait for the runner to become Idle.
2. Stop the Windows service.
3. Use **Settings > Actions > Runners** to obtain a short-lived removal or registration token.
4. Run the runner distribution's documented `config.cmd remove` or `config.cmd` command locally from its installation directory.
5. Enter the one-time token only in the local interactive prompt. Never paste it into an issue, pull request, chat, shell transcript, workflow, file, or CI log.
6. Reinstall the service under `NT AUTHORITY\NETWORK SERVICE`, restore the exact four labels, restart it, and run preflight before accepting required jobs.
7. Treat old runner credentials and diagnostic output as sensitive host state; remove them locally according to GitHub's runner documentation, never through a repository workflow.

## Rollback to GitHub-hosted runners

When hosted billing capacity returns, open a reviewed rollback pull request that changes each affected `runs-on` value back to its prior hosted target. Preserve every workflow name and job/check name, retain least-privilege permissions and pinned actions, and rerun the complete required set. Confirm branch protection still names the same checks before merging the rollback.

After the rollback is active and no self-hosted job is queued or Active, stop or remove the runner using the procedures above. Do not delete registration state while a job is running.
