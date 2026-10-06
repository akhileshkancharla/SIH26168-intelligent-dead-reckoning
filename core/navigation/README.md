# Native navigation build

Issue #38 wires the accepted S2 navigation implementation into the repository
native build. It uses CMake 3.20 or newer, requires C++20 without compiler
extensions, and supports the Visual Studio 2022 x64 toolchain used by CI.

## Pinned dependency

The build fetches Eigen 3.4.0 from the official
`https://gitlab.com/libeigen/eigen.git` repository at immutable commit
`3147391d946bb4b6c68edd901f2add6ac1f31f8c`. Configuration reads Eigen's
version macros and fails unless the resolved version is exactly 3.4.0. The
first clean configuration therefore requires Git and network access. CMake
stores the fetched source only under the selected, ignored build directory.

## Windows x64 build and test

From the repository root, use a new build directory:

```powershell
cmake -S . -B build/wp-03-2 -G "Visual Studio 17 2022" -A x64 -T host=x64
cmake --build build/wp-03-2 --config Release
ctest --test-dir build/wp-03-2 -C Release --output-on-failure
```

Delete the ignored build directory and repeat these commands for an independent
clean-build check. The `host=x64` toolset selection keeps the compiler process
64-bit and avoids the heap limit previously observed with the imported Eigen
templates. CMake rejects an MSVC configuration that omits either x64 setting.

The build produces:

- `sih26168_navigation_core`: the portable production S2 static library.
- `sih26168_navigation_core_tests`: the imported deterministic native checks,
  registered with CTest as `navigation-core-native`.
- `sih26168_navigation_replay`: the host replay executable.
- `sih26168_navigation_smoke` and `sih26168_navigation_smoke_test`: the existing
  repository smoke library and CTest `navigation-smoke`.

The production library exports only `core/navigation/include` and Eigen's
header-only target to consumers. Python and NumPy remain offline verification
tools and are not CMake or production dependencies.

For WP-07.4, `NavigationCore::screen()` uses the same validated I-12 input
and S2 innovation gate as `update()`. It leaves scientific state and covariance
unchanged, but C-07 consumes the canonical measurement ID and sequence on first
presentation, even when screening rejects the input. A passing screen is not
an accepted update and that ID cannot later be upgraded through `update()` or
a reconstructed C-09 gate. Earlier return candidates are screened and withheld;
the independent final candidate goes directly to C-07's atomic innovation gate
and update after the configured dwell. `navigation-core-api` covers state and
covariance non-mutation, evidence-once ownership, direct-update bypass rejection,
and a separate final-candidate NIS comparison.

## Portable public API

Issue #39 defines the public C++20 contract in
`include/sih26168/navigation_core.hpp`. It deliberately exposes standard-library
value types rather than Eigen or Android/JNI types. Source and callback-arrival
timestamps use distinct strong types in the same boot-scoped monotonic
nanosecond domain. Sequence and evidence identifiers are explicit, coordinate
frames and SI units are documented at every boundary, and propagation and
measurement decisions use typed results.

`sih26168::navigation::NavigationCore` exclusively owns the accepted S2 core,
operational biases, covariance and presented-evidence ledger. State and
covariance are returned only as value snapshots, so callers cannot mutate the
internal estimate. A nonempty evidence ID is consumed on first presentation,
including precheck-invalid and rejected measurements. The wrapper performs no
unit conversion and does not change the accepted estimator equations, noise
values or innovation gates.

The API makes no stable binary-ABI promise. Issue #40 may adapt this value
contract to JNI later without adding Android types or JNI lifecycle concerns to
the portable core.

This work does not add JNI assigned to issue #40 or claim the C++/NumPy parity
work assigned to issue #41. The replay executable is a host verification
driver; Android integration remains outside this build.
