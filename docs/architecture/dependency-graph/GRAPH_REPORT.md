# Sanitized Graphify Dependency Report

## Snapshot metadata

- Snapshot classification: `generated-and-sanitized`
- Source repository: `akhileshkancharla/SIH26168-intelligent-dead-reckoning`
- Source branch: `issue/WP-02.1-wp-02-1-import-validated`
- Source parent commit: `5c5e0b9ce5cc419735612b682a7b26bfe36eb1ee`
- Graphify version: `0.9.53`
- Graphify mode: code-only static extraction; semantic document extraction disabled
- Counts: 4017 nodes, 6597 edges, 273 communities
- Edge evidence: 6432 extracted, 165 inferred
- CI mode: `snapshot-validation-only`

## VERIFIED FROM CODE

The repository contains the accepted portable S2 navigation core and host-side native test/replay entry points. No integrated raw-sensor-to-position application path exists; Android startup still renders a replay-labelled scaffold.

The C++ core is host-buildable, while Android acquisition, JNI, training, map, and analyzer integration remain disconnected or placeholders. This statement describes current implementation, not the intended Revision 3 architecture.

### Major modules

| Module | Extracted source files | Current interpretation |
| --- | ---: | --- |
| Android app | 20 | Launcher/UI scaffold; no sensor-to-position path |
| Android JNI adapter | 5 | Native boundary; not connected to the imported S1 logger |
| Standalone S1 acquisition | 18 | Imported logger and analyzer; no integrated GNSS-to-position path |
| Other Android files | 2 | Android build/configuration files outside the app, JNI, and S1 import |
| Portable core | 39 | Host-buildable S2 core plus contract smoke |
| Contracts | 24 | Bootstrap replay schema and enum artifacts |
| Repository automation | 14 | Repository and GitHub governance tooling |
| Policy CI | 16 | Repository validation and generated-file checks |
| Training/maps and top-level analyzer | 0 | No integrated source files in these top-level modules |

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
| `ReplayNavigationViewModel` | 59 | [android/app/src/main/java/org/sih26168/app/replay/ReplayNavigationViewModel.kt:L16](../../../android/app/src/main/java/org/sih26168/app/replay/ReplayNavigationViewModel.kt) |
| `MapLibreMapViewport.kt` | 39 | [android/app/src/main/java/org/sih26168/app/ui/map/MapLibreMapViewport.kt:L1](../../../android/app/src/main/java/org/sih26168/app/ui/map/MapLibreMapViewport.kt) |
| `configure_project.mjs` | 37 | [tools/bootstrap/configure_project.mjs:L1](../../../tools/bootstrap/configure_project.mjs) |
| `RecordingService` | 35 | [android/acquisition/imported/S1_Android_Acquisition_Spike/app/src/main/java/org/sih26168/s1logger/RecordingService.kt:L16](../../../android/acquisition/imported/S1_Android_Acquisition_Spike/app/src/main/java/org/sih26168/s1logger/RecordingService.kt) |
| `generate_contract_bindings.py` | 35 | [ci/generate_contract_bindings.py:L1](../../../ci/generate_contract_bindings.py) |
| `LocationFix` | 32 | [core/gnss/include/sih26168/gnss/fix_precheck.hpp:L16](../../../core/gnss/include/sih26168/gnss/fix_precheck.hpp) |
| `ReplayNavigationViewModelTest` | 31 | [android/app/src/test/java/org/sih26168/app/replay/ReplayNavigationViewModelTest.kt:L12](../../../android/app/src/test/java/org/sih26168/app/replay/ReplayNavigationViewModelTest.kt) |
| `reference_oracle.py` | 31 | [core/navigation/verification/python/reference_oracle.py:L1](../../../core/navigation/verification/python/reference_oracle.py) |
| `ReplayNavigationShell.kt` | 29 | [android/app/src/main/java/org/sih26168/app/ui/ReplayNavigationShell.kt:L1](../../../android/app/src/main/java/org/sih26168/app/ui/ReplayNavigationShell.kt) |
| `AlignmentEstimate` | 28 | [core/include/sih26168/contracts/alignment_estimate.hpp:L15](../../../core/include/sih26168/contracts/alignment_estimate.hpp) |

### Weakly connected or orphan candidates

The raw Graphify report identified 1312 isolated symbol nodes. This sanitizer independently found 1627 repository-backed nodes with degree at most one; the bounded sample below is diagnostic, not deletion evidence.

| Node | Degree | Source |
| --- | ---: | --- |
| `S1_Android_Acquisition_Spike/app/build.gradle.kts` | 0 | [android/acquisition/imported/S1_Android_Acquisition_Spike/app/build.gradle.kts](../../../android/acquisition/imported/S1_Android_Acquisition_Spike/app/build.gradle.kts) |
| `S1_Android_Acquisition_Spike/build.gradle.kts` | 0 | [android/acquisition/imported/S1_Android_Acquisition_Spike/build.gradle.kts](../../../android/acquisition/imported/S1_Android_Acquisition_Spike/build.gradle.kts) |
| `S1_Android_Acquisition_Spike/settings.gradle.kts` | 0 | [android/acquisition/imported/S1_Android_Acquisition_Spike/settings.gradle.kts](../../../android/acquisition/imported/S1_Android_Acquisition_Spike/settings.gradle.kts) |
| `android/app/build.gradle.kts` | 0 | [android/app/build.gradle.kts](../../../android/app/build.gradle.kts) |
| `android/build.gradle.kts` | 0 | [android/build.gradle.kts](../../../android/build.gradle.kts) |
| `android/settings.gradle.kts` | 0 | [android/settings.gradle.kts](../../../android/settings.gradle.kts) |
| `update_manifest.py` | 0 | [ci/update_manifest.py](../../../ci/update_manifest.py) |
| `verify_repository.ps1` | 0 | [ci/verify_repository.ps1](../../../ci/verify_repository.ps1) |
| `smoke.cpp` | 0 | [core/navigation/src/smoke.cpp](../../../core/navigation/src/smoke.cpp) |
| `run_parity.ps1` | 0 | [core/navigation/verification/run_parity.ps1](../../../core/navigation/verification/run_parity.ps1) |
| `sih26168-bootstrap` | 0 | [pyproject.toml](../../../pyproject.toml) |
| `sih26168_bootstrap/__init__.py` | 0 | [tools/bootstrap/src/sih26168_bootstrap/__init__.py](../../../tools/bootstrap/src/sih26168_bootstrap/__init__.py) |
| `tests/__init__.py` | 0 | [tools/dataset/tests/__init__.py](../../../tools/dataset/tests/__init__.py) |
| `analyzer/__init__.py` | 1 | [android/acquisition/imported/S1_Android_Acquisition_Spike/analyzer/__init__.py](../../../android/acquisition/imported/S1_Android_Acquisition_Spike/analyzer/__init__.py) |
| `S1 Android acquisition analyzer.` | 1 | [android/acquisition/imported/S1_Android_Acquisition_Spike/analyzer/__init__.py](../../../android/acquisition/imported/S1_Android_Acquisition_Spike/analyzer/__init__.py) |

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
