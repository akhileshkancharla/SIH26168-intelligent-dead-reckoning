# WP-07.4 reacquisition evidence

## Scope and correction

- Issue #64, related to parent #8. The branch is based on `origin/main` at
  `869d7696fce6a60c0009d3943da9e1c25f22a23a`.
- Review correction: C-07 now consumes each canonical I-12 measurement ID and
  sequence on first `screen()` or `update()` presentation, including rejection.
  A screen does not change scientific state or covariance. C-09 no longer keeps
  a shadow canonical measurement-ID set.
- Earlier eligible return candidates are screened and withheld. The independent
  candidate that completes the configured dwell goes directly to C-07's atomic
  innovation gate and update, without first screening that same ID. Recovery
  still requires a successful C-07 update and the independent C-09 health rule.
- Direct-update bypass, malformed-screen upgrade, duplicate canonical identity,
  and reconstructed-gate regressions exercise C-07 evidence-once ownership.

## Checks on the corrected working tree

- Repository verification: `python ci/verify_repository.py all` and `forbidden`
  passed. `python ci/generate_contract_bindings.py --check`,
  `python tools/graphify/verify_graph.py`, and `git diff --check` passed.
- Graphify workflow unit tests passed **14/14**. A direct run of the bootstrap
  unittest directory was not a passing suite in this bare Python environment:
  35 tests were discovered, five failed to import because `jsonschema` was not
  installed, and one integration test was skipped because the project package
  was not installed. The CI Python lane must supply its declared dependencies.
- Pinned Graphifyy `0.9.53` ran twice from the unchanged corrected source tree.
  All four sanitized graph artifacts and the refreshed repository manifest were
  byte-identical across the two runs: **4,292 nodes, 7,138 edges, 296
  communities**. `graph.json` SHA-256:
  `b6ebf377184fdaa16d3355daf7f29283251d429ad223b4e76ea8aee3e8a05dce`;
  `metadata.json` SHA-256:
  `261bc1f416c79bde04f185a133f703e69ff2ed22ec5b0d31815fd1427b6602c8`;
  repository-manifest SHA-256:
  `4f8ab4aca9aef370943d40897fb43dfa23921abb36a5dd3f6028c823d922a162`.
- MSVC 2019 C++20 syntax checks passed for the corrected C-09 implementation,
  both focused test translation units, and the modified C-07 API translation
  unit. Focused executable tests passed: **27/27** navigation API cases and
  **12/12** GNSS reacquisition cases. Those executables linked the corrected
  C-07/C-09 source against a previously built S2 core library; its underlying
  `navigation_core.cpp` and `s2_oracle/navigation_core.hpp` bytes match the
  current source tree (SHA-256 `554881d0f948a0f7795a13c7667b0ec8f3351d4b95d7bf3a36f92631671027c3`
  and `1a00e6f625d9035d1da36c12d10c720586a98bc76e0afed26bb940868c8afc7b`).
  This is a focused supplementary check, **not** a clean full native build.

## Not yet passed on this corrected tree

- A clean x64 Visual Studio 2019 CMake configure succeeded with the pinned
  Eigen 3.4.0 source at commit `3147391d946bb4b6c68edd901f2add6ac1f31f8c`.
  Full Release and focused Debug builds were environment-blocked before tests:
  MSVC failed in Eigen/S2 compilation with `fatal error C1060: compiler is out
  of heap space`. The shell also exposed duplicate `Path`/`PATH` entries that
  initially caused MSBuild `MSB6001`; a sanitized child environment got past
  that first obstacle but did not resolve the compiler memory failure.
  Therefore **CTest has not run on a clean build of this corrected tree**.
- The earlier branch head's 12/12 CTest result is historical and must not be
  treated as current-head proof. Current-head required CI, including the
  supported Windows C++ and Android lanes, must run after the signed commit is
  pushed. The existing Graphify partial Kotlin-parse warning is a static
  extraction limitation, not a passing Android test.

## Scientific and integration limits

OD-09 operational thresholds remain provisional and must be frozen from
fixture/device evidence. This host module accepts a caller-provided C-09
`HEALTHY` attestation; it does not authenticate that upstream policy. There is
no live Android wiring, finalized I-15 serialization, physical-device run,
route/accuracy result, or release-gate claim in this PR.
