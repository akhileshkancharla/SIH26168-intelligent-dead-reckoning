# Sanitized Graphify Dependency Report

## Snapshot metadata

- Snapshot classification: `generated-and-sanitized`
- Source repository: `akhileshkancharla/SIH26168-intelligent-dead-reckoning`
- Source branch: `chore/author-aware-review-policy`
- Source parent commit: `6af81b4f16486bf79a4239e71697032db24e8ec3`
- Graphify version: `0.9.53`
- Graphify mode: code-only static extraction; semantic document extraction disabled
- Counts: 238 nodes, 394 edges, 28 communities
- Edge evidence: 383 extracted, 11 inferred
- CI mode: `snapshot-validation-only`

## VERIFIED FROM CODE

The repository is presently a bootstrap and governance scaffold. No executable raw-sensor-to-position navigation path exists. Android startup renders a replay-labelled scaffold, and the native core exposes only a contract-version smoke function.

Android, core, acquisition, JNI, training, map, and analyzer areas remain disconnected or placeholders. This statement describes current implementation, not the intended Revision 3 architecture.

### Major modules

| Module | Extracted source files | Current interpretation |
| --- | ---: | --- |
| Android app | 5 | Launcher/UI scaffold; no sensor-to-position path |
| Portable core | 3 | C++ contract-version smoke scaffold |
| Contracts | 1 | Bootstrap replay schema and enum artifacts |
| Repository automation | 6 | Repository and GitHub governance tooling |
| Policy CI | 6 | Repository validation and generated-file checks |
| Acquisition/JNI/ML/maps/analyzer | 0 | README-only or disconnected placeholders |

### Entry points

- Android: [`MainActivity.onCreate`](../../../android/app/src/main/java/org/sih26168/app/MainActivity.kt)
- C++ smoke test: [`core/navigation/tests/smoke_test.cpp`](../../../core/navigation/tests/smoke_test.cpp)
- Repository verifier: [`ci/verify_repository.py`](../../../ci/verify_repository.py)
- Bootstrap generator: [`tools/bootstrap/generate_repository.py`](../../../tools/bootstrap/generate_repository.py)

### Actual dependency paths

- Android launcher → `MainActivity.onCreate` → scaffold `TextView`.
- C++ smoke test → `contract_version()` → fixed bootstrap version comparison.
- Synthetic replay fixture → bootstrap smoke/policy validation.
- There is no extracted IMU/GNSS ingestion → preprocessing → state-estimation → position-output path.

## VERIFIED FROM GRAPH

Current high-degree nodes are primarily repository administration tooling, not navigation runtime modules.

### High-degree nodes

| Node | Degree | Source |
| --- | ---: | --- |
| `configure_project.mjs` | 37 | [tools/bootstrap/configure_project.mjs:L1](../../../tools/bootstrap/configure_project.mjs) |
| `sanitize_graph.py` | 27 | [tools/graphify/sanitize_graph.py:L1](../../../tools/graphify/sanitize_graph.py) |
| `configure_github.py` | 19 | [tools/bootstrap/configure_github.py:L1](../../../tools/bootstrap/configure_github.py) |
| `generate_repository.py` | 15 | [tools/bootstrap/generate_repository.py:L1](../../../tools/bootstrap/generate_repository.py) |
| `Any` | 14 | external/unlocated symbol |
| `verify_repository.py` | 13 | [ci/verify_repository.py:L1](../../../ci/verify_repository.py) |
| `generate_snapshot()` | 13 | [tools/graphify/sanitize_graph.py:L564](../../../tools/graphify/sanitize_graph.py) |
| `Path` | 13 | external/unlocated symbol |
| `verify_graph.py` | 13 | [tools/graphify/verify_graph.py:L1](../../../tools/graphify/verify_graph.py) |
| `configure_issues()` | 10 | [tools/bootstrap/configure_github.py:L332](../../../tools/bootstrap/configure_github.py) |

### Weakly connected or orphan candidates

The raw Graphify report identified 52 isolated symbol nodes. This sanitizer independently found 85 repository-backed nodes with degree at most one; the bounded sample below is diagnostic, not deletion evidence.

| Node | Degree | Source |
| --- | ---: | --- |
| `app/build.gradle.kts` | 0 | [android/app/build.gradle.kts](../../../android/app/build.gradle.kts) |
| `android/build.gradle.kts` | 0 | [android/build.gradle.kts](../../../android/build.gradle.kts) |
| `settings.gradle.kts` | 0 | [android/settings.gradle.kts](../../../android/settings.gradle.kts) |
| `generate_contract_bindings.py` | 0 | [ci/generate_contract_bindings.py](../../../ci/generate_contract_bindings.py) |
| `update_manifest.py` | 0 | [ci/update_manifest.py](../../../ci/update_manifest.py) |
| `verify_repository.ps1` | 0 | [ci/verify_repository.ps1](../../../ci/verify_repository.ps1) |
| `smoke.cpp` | 0 | [core/navigation/src/smoke.cpp](../../../core/navigation/src/smoke.cpp) |
| `sih26168-bootstrap` | 0 | [pyproject.toml](../../../pyproject.toml) |
| `__init__.py` | 0 | [tools/bootstrap/src/sih26168_bootstrap/__init__.py](../../../tools/bootstrap/src/sih26168_bootstrap/__init__.py) |
| `ReplayDisclosure` | 1 | [android/app/src/main/java/org/sih26168/app/MainActivity.kt](../../../android/app/src/main/java/org/sih26168/app/MainActivity.kt) |
| `ReplayDisclosureTest.kt` | 1 | [android/app/src/test/java/org/sih26168/app/ReplayDisclosureTest.kt](../../../android/app/src/test/java/org/sih26168/app/ReplayDisclosureTest.kt) |
| `.replayLabelIsUnmistakable()` | 1 | [android/app/src/test/java/org/sih26168/app/ReplayDisclosureTest.kt](../../../android/app/src/test/java/org/sih26168/app/ReplayDisclosureTest.kt) |
| `governance_selftest.py` | 1 | [ci/governance_selftest.py](../../../ci/governance_selftest.py) |
| `inactivity()` | 1 | [ci/governance_selftest.py](../../../ci/governance_selftest.py) |
| `contracts()` | 1 | [ci/verify_repository.py](../../../ci/verify_repository.py) |

### Cycles

No import cycles were extracted.

## INFERRED FROM ARCHITECTURE

Revision 3 intends acquisition, preprocessing, a single-owner S2 C++ core, integrity/reacquisition, optional learned/map proposals, and separate scientific/display outputs. Those intended relationships must not be mistaken for implemented dependencies.

## PROPOSED IMPROVEMENT

Use the graph with source inspection to establish cross-module contracts as implementation proceeds. Do not add inferred runtime edges merely to make the graph resemble the intended design.

## Known limitations

- The snapshot uses local code-only AST extraction; documentation is interpreted separately.
- The committed snapshot and bootstrap repository manifest are excluded from extraction to avoid generated-artifact recursion.
- Static extraction cannot prove absence of JNI, Android callback, manifest, reflection, generated-code, dependency-injection, resource, or serialized-contract relationships.
- Empty and README-only modules may not appear as graph communities.
- Graphify cannot prove runtime reachability, correctness, performance, or scientific validity.
- Node and edge counts are tool-version and extraction-mode dependent.
- `graph.html` is not committed because the portable JSON/report snapshot is the reviewed artifact and HTML determinism has not been established.

## Architecture interpretation warning

Architecture Revision 3 is authoritative. Graphify is supporting static evidence only. C-07 remains the sole owner of S2 navigation state, operational biases, covariance, and evidence acceptance; ML and map components can submit bounded proposals but cannot overwrite the core.

## Regeneration

From the repository root, use `tools/graphify/update_graph.ps1` on Windows or `tools/graphify/update_graph.sh` on Unix with the configured Graphify version available. The wrapper updates raw local output, sanitizes the shared snapshot, verifies it, and refreshes checksums.
