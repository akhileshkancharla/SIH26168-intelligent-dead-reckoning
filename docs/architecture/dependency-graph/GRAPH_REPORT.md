# Sanitized Graphify Dependency Report

## Snapshot metadata

- Snapshot classification: `generated-and-sanitized`
- Source repository: `akhileshkancharla/SIH26168-intelligent-dead-reckoning`
- Source branch: `issue/WP-09.6-wp-09-6-verify-complete`
- Source parent commit: `276592dc0ea3e491d1ec286a14f40fb9cbe2b14d`
- Graphify version: `0.9.53`
- Graphify mode: code-only static extraction; semantic document extraction disabled
- Counts: 4090 nodes, 6841 edges, 273 communities
- Edge evidence: 6611 extracted, 230 inferred
- CI mode: `snapshot-validation-only`

## VERIFIED FROM CODE

The repository contains the accepted portable S2 navigation core and host-side native test/replay entry points. No integrated raw-sensor-to-position application path exists; Android startup still renders a replay-labelled scaffold.

The C++ core is host-buildable, while Android acquisition, JNI, training, map, and analyzer integration remain disconnected or placeholders. This statement describes current implementation, not the intended Revision 3 architecture.

### Major modules

| Module | Extracted source files | Current interpretation |
| --- | ---: | --- |
| Android app | 29 | Launcher/UI scaffold; no sensor-to-position path |
| Portable core | 45 | Host-buildable S2 core plus contract smoke |
| Contracts | 24 | Bootstrap replay schema and enum artifacts |
| Repository automation | 14 | Repository and GitHub governance tooling |
| Policy CI | 15 | Repository validation and generated-file checks |
| Acquisition/JNI/ML/maps/analyzer | 0 | README-only or disconnected placeholders |

### Entry points

- Android: [`MainActivity.onCreate`](../../../android/app/src/main/java/org/sih26168/app/MainActivity.kt)
- C++ smoke test: [`core/navigation/tests/smoke_test.cpp`](../../../core/navigation/tests/smoke_test.cpp)
- C++ S2 native test: [`core/navigation/tests/test_navigation_core.cpp`](../../../core/navigation/tests/test_navigation_core.cpp)
- C++ S2 replay driver: [`core/navigation/verification/replay_main.cpp`](../../../core/navigation/verification/replay_main.cpp)
- Repository verifier: [`ci/verify_repository.py`](../../../ci/verify_repository.py)
- Bootstrap generator: [`tools/bootstrap/generate_repository.py`](../../../tools/bootstrap/generate_repository.py)

### Actual dependency paths

- Android launcher → `MainActivity.onCreate` → scaffold `TextView`.
- C++ smoke test → `contract_version()` → fixed bootstrap version comparison.
- CMake `sih26168_navigation_core` target → accepted S2 source and private headers → pinned Eigen 3.4.0 headers.
- CMake native-test and replay targets → `sih26168_navigation_core`; Python/NumPy remains outside these production build targets.
- Synthetic replay fixture → bootstrap smoke/policy validation.
- There is no extracted IMU/GNSS ingestion → preprocessing → state-estimation → position-output path.
- CMake target relationships are verified from `core/navigation/CMakeLists.txt`; code-only Graphify extraction does not model the CMake target graph as edges.

## VERIFIED FROM GRAPH

Current high-degree nodes are primarily repository administration tooling, not navigation runtime modules.

### High-degree nodes

| Node | Degree | Source |
| --- | ---: | --- |
| `ReplayNavigationViewModel` | 71 | [android/app/src/main/java/org/sih26168/app/replay/ReplayNavigationViewModel.kt:L16](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayNavigationViewModel.kt) |
| `ReplayNavigationShell.kt` | 43 | [android/app/src/main/java/org/sih26168/app/ui/ReplayNavigationShell.kt:L1](../../../android/app/src/main/java/org/sih26168/app/ui/ReplayNavigationShell.kt) |
| `MapLibreMapViewport.kt` | 42 | [android/app/src/main/java/org/sih26168/app/ui/map/MapLibreMapViewport.kt:L1](../../../android/app/src/main/java/org/sih26168/app/ui/map/MapLibreMapViewport.kt) |
| `ReplayNavigationViewModelTest` | 39 | [android/app/src/test/java/org/sih26168/app/replay/ReplayNavigationViewModelTest.kt:L19](../../../android/app/src/test/java/org/sih26168/app/replay/ReplayNavigationViewModelTest.kt) |
| `configure_project.mjs` | 37 | [tools/bootstrap/configure_project.mjs:L1](../../../tools/bootstrap/configure_project.mjs) |
| `LocationFix` | 36 | [core/gnss/include/sih26168/gnss/fix_precheck.hpp:L16](../../../core/gnss/include/sih26168/gnss/fix_precheck.hpp) |
| `generate_contract_bindings.py` | 35 | [ci/generate_contract_bindings.py:L1](../../../ci/generate_contract_bindings.py) |
| `ReplayUiState` | 33 | [android/app/src/main/java/org/sih26168/app/replay/ReplayUiState.kt:L85](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayUiState.kt) |
| `reference_oracle.py` | 31 | [core/navigation/verification/python/reference_oracle.py:L1](../../../core/navigation/verification/python/reference_oracle.py) |
| `ReplayIntent` | 28 | [android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt:L59](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt) |

### Weakly connected or orphan candidates

The raw Graphify report identified 1366 isolated symbol nodes. This sanitizer independently found 1674 repository-backed nodes with degree at most one; the bounded sample below is diagnostic, not deletion evidence.

| Node | Degree | Source |
| --- | ---: | --- |
| `app/build.gradle.kts` | 0 | [android/app/build.gradle.kts](../../../android/app/build.gradle.kts) |
| `android/build.gradle.kts` | 0 | [android/build.gradle.kts](../../../android/build.gradle.kts) |
| `settings.gradle.kts` | 0 | [android/settings.gradle.kts](../../../android/settings.gradle.kts) |
| `update_manifest.py` | 0 | [ci/update_manifest.py](../../../ci/update_manifest.py) |
| `verify_repository.ps1` | 0 | [ci/verify_repository.ps1](../../../ci/verify_repository.ps1) |
| `smoke.cpp` | 0 | [core/navigation/src/smoke.cpp](../../../core/navigation/src/smoke.cpp) |
| `run_parity.ps1` | 0 | [core/navigation/verification/run_parity.ps1](../../../core/navigation/verification/run_parity.ps1) |
| `sih26168_bootstrap/__init__.py` | 0 | [tools/bootstrap/src/sih26168_bootstrap/__init__.py](../../../tools/bootstrap/src/sih26168_bootstrap/__init__.py) |
| `dataset/tests/__init__.py` | 0 | [tools/dataset/tests/__init__.py](../../../tools/dataset/tests/__init__.py) |
| `DUPLICATE_EVIDENCE_ID` | 1 | [android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt](../../../android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt) |
| `NEGATIVE_SEQUENCE` | 1 | [android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt](../../../android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt) |
| `NON_INCREASING_STREAM_SEQUENCE` | 1 | [android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt](../../../android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt) |
| `REENTRANT_SUBMISSION` | 1 | [android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt](../../../android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt) |
| `SOURCE_MODE_MISMATCH` | 1 | [android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt](../../../android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt) |
| `UNSUPPORTED_PAYLOAD_TYPE` | 1 | [android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt](../../../android/app/src/main/java/org/sih26168/app/ingress/SharedNavigationIngress.kt) |

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
