# WP-07.4 host implementation evidence

- Scope: issue #64, reacquisition consistency and dwell only. Parent: #8.
- Source baseline: `origin/main` at `869d7696fce6a60c0009d3943da9e1c25f22a23a`.
- Toolchain: Visual Studio 2019 Build Tools, x64 Release; CMake 3.20.21032501; repository-pinned Eigen 3.4.0 at `3147391d946bb4b6c68edd901f2add6ac1f31f8c`.
- Reproduction: `cmake -S . -B <outside-repo-build> -G "Visual Studio 16 2019" -A x64 -T host=x64`; `cmake --build <outside-repo-build> --config Release`; `ctest --test-dir <outside-repo-build> -C Release --output-on-failure`.
- Result: clean full native build and CTest 12/12 passed, including the new `gnss-reacquisition-native` and existing navigation/GNSS/JNI tests. The new native scenarios cover first-fix withholding, later recovery, biased return, intermittent return, source/canonical duplicates, malformed measurement lineage, non-healthy C-09 screening, and policy-supplied dwell count.
- Boundary: the first return only invokes C-07's non-mutating screening API; exact C-07 state, covariance and evidence-ledger non-mutation are asserted. Recovery requires a later independent C-09 `HEALTHY` attestation, a positive count/time dwell, and an actual successful C-07 update. The GNSS screen never directly writes C-07 state.
- Limitations: OD-09 operational thresholds remain provisional and must be frozen from fixture/device evidence. C-09 `HEALTHY` is supplied by the caller, not authenticated by this host module. No Android live wiring, finalized I-15 serializer, physical-device, route, accuracy, or release-gate claim is made. The local build used VS2019 because VS2022 C++ components were unavailable here; the repository CI runner must validate its supported VS2022 toolchain after the PR is pushed.
