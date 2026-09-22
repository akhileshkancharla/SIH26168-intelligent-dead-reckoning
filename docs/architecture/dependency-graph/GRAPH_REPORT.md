# Sanitized Graphify Dependency Report

## Snapshot metadata

- Snapshot classification: `generated-and-sanitized`
- Source repository: `akhileshkancharla/SIH26168-intelligent-dead-reckoning`
- Source branch: `issue/WP-10.2-wp-10-2-implement-six`
- Source parent commit: `cd2e977eb1bb304d0eb3b2010a06c03e5993941a`
- Graphify version: `0.9.53`
- Graphify mode: code-only static extraction; semantic document extraction disabled
- Counts: 2123 nodes, 3326 edges, 168 communities
- Edge evidence: 3260 extracted, 66 inferred
- CI mode: `snapshot-validation-only`

## VERIFIED FROM CODE

The repository contains the accepted portable S2 navigation core and host-side native test/replay entry points. No integrated raw-sensor-to-position application path exists; Android startup still renders a replay-labelled scaffold.

The C++ core is host-buildable, while Android acquisition, JNI, training, map, and analyzer integration remain disconnected or placeholders. This statement describes current implementation, not the intended Revision 3 architecture.

### Major modules

| Module | Extracted source files | Current interpretation |
| --- | ---: | --- |
| Android app | 15 | Launcher/UI scaffold; no sensor-to-position path |
| Portable core | 22 | Host-buildable S2 core plus contract smoke |
| Contracts | 23 | Bootstrap replay schema and enum artifacts |
| Repository automation | 12 | Repository and GitHub governance tooling |
| Policy CI | 14 | Repository validation and generated-file checks |
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
| `configure_project.mjs` | 37 | [tools/bootstrap/configure_project.mjs:L1](../../../tools/bootstrap/configure_project.mjs) |
| `generate_contract_bindings.py` | 35 | [ci/generate_contract_bindings.py:L1](../../../ci/generate_contract_bindings.py) |
| `MapLibreMapViewport.kt` | 33 | [android/app/src/main/java/org/sih26168/app/ui/map/MapLibreMapViewport.kt:L1](../../../android/app/src/main/java/org/sih26168/app/ui/map/MapLibreMapViewport.kt) |
| `reference_oracle.py` | 31 | [core/navigation/verification/python/reference_oracle.py:L1](../../../core/navigation/verification/python/reference_oracle.py) |
| `ReplayNavigationViewModel` | 30 | [android/app/src/main/java/org/sih26168/app/replay/ReplayNavigationViewModel.kt:L9](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayNavigationViewModel.kt) |
| `sanitize_graph.py` | 27 | [tools/graphify/sanitize_graph.py:L1](../../../tools/graphify/sanitize_graph.py) |
| `InitialState` | 26 | [core/navigation/include/sih26168/navigation_core.hpp:L104](../../../core/navigation/include/sih26168/navigation_core.hpp) |
| `navigation_api.cpp` | 26 | [core/navigation/src/navigation_api.cpp:L1](../../../core/navigation/src/navigation_api.cpp) |
| `MeasurementInput` | 24 | [core/navigation/include/sih26168/navigation_core.hpp:L141](../../../core/navigation/include/sih26168/navigation_core.hpp) |
| `run_python_tests.py` | 24 | [core/navigation/verification/python/run_python_tests.py:L1](../../../core/navigation/verification/python/run_python_tests.py) |

### Weakly connected or orphan candidates

The raw Graphify report identified 782 isolated symbol nodes. This sanitizer independently found 943 repository-backed nodes with degree at most one; the bounded sample below is diagnostic, not deletion evidence.

| Node | Degree | Source |
| --- | ---: | --- |
| `app/build.gradle.kts` | 0 | [android/app/build.gradle.kts](../../../android/app/build.gradle.kts) |
| `android/build.gradle.kts` | 0 | [android/build.gradle.kts](../../../android/build.gradle.kts) |
| `settings.gradle.kts` | 0 | [android/settings.gradle.kts](../../../android/settings.gradle.kts) |
| `update_manifest.py` | 0 | [ci/update_manifest.py](../../../ci/update_manifest.py) |
| `verify_repository.ps1` | 0 | [ci/verify_repository.ps1](../../../ci/verify_repository.ps1) |
| `smoke.cpp` | 0 | [core/navigation/src/smoke.cpp](../../../core/navigation/src/smoke.cpp) |
| `sih26168-bootstrap` | 0 | [pyproject.toml](../../../pyproject.toml) |
| `sih26168_bootstrap/__init__.py` | 0 | [tools/bootstrap/src/sih26168_bootstrap/__init__.py](../../../tools/bootstrap/src/sih26168_bootstrap/__init__.py) |
| `tests/__init__.py` | 0 | [tools/dataset/tests/__init__.py](../../../tools/dataset/tests/__init__.py) |
| `Pause` | 1 | [android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt) |
| `Play` | 1 | [android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt) |
| `PresentTelemetry` | 1 | [android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt) |
| `Reset` | 1 | [android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt) |
| `SetSpeedMultiplier` | 1 | [android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt) |
| `Step` | 1 | [android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayIntent.kt) |

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
