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

This work does not define the portable public API assigned to issue #39, add
JNI assigned to issue #40, or claim the C++/NumPy parity work assigned to issue
#41. The replay executable is a host verification driver; Android integration
remains outside this build.
