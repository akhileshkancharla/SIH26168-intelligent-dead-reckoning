# S2 offline verification

This directory contains the accepted S2 replay driver, deterministic synthetic
fixtures, and independent NumPy oracle/checks imported by WP-03.1.

It is test/offline code. Production C++ does not import, bind, invoke, or
otherwise depend on Python. The NumPy oracle does not import, bind, or invoke
C++. `run_parity.ps1` is an external verification orchestrator: it executes the
already-built C++ replay first and then executes the NumPy comparison over the
replay's ordinary CSV files.

## Accepted inputs and tolerances

The only parity inputs are the accepted synthetic fixtures in `fixtures/`.
`scenario_manifest.json` records their generator seed and canonical hashes.
The comparison uses the tolerances already frozen in the accepted S2
`check_parity.py` import; WP-03.5 does not tune them from observed results:

| Field | Absolute tolerance |
| --- | ---: |
| Position component | `2e-9 m` |
| Velocity component | `2e-9 m/s` |
| Quaternion orientation distance | `2e-10 rad` |
| Accelerometer-bias component | `2e-10 m/s^2` |
| Gyroscope-bias component | `2e-10 rad/s` |
| Covariance element | `2e-9` in the applicable squared S2 units |
| Innovation component | `2e-9` in the applicable measurement unit |
| NIS | `2e-9` |

Quaternion comparison uses sign-equivalent rotation distance. Covariance is
checked as a complete 15x15 matrix in the frozen S2 ordering; the report also
records both diagonals, maximum index/value difference, and symmetry error.
Measurement evidence IDs, timestamps, input order, status, accepted/rejected
decision, and duplicate decision must match exactly.

Every applicable state, quaternion, covariance, innovation, and NIS value must
be finite on both sides. A non-finite value or one-sided finiteness mismatch is
recorded as strict JSON `null`, fails its per-record comparison, increments the
aggregate non-finite count, and fails the final verdict. NIS is explicitly
`not_applicable` only for a zero-dimension decision where both implementations
omit it.

The accepted replay fixture includes position, velocity, combined updates, a
biased rejected return, duplicate evidence, irregular sampling, and one valid
gap. The existing native and NumPy unit suites separately cover invalid,
non-finite, and non-increasing propagation/update inputs that are deliberately
absent from the accepted replay CSV. No new scientific fixture is invented by
WP-03.5.

## Reproduce

Configure and build the repository using the pinned procedure in
`core/navigation/README.md`, then run the native suite and two independent
parity output directories:

The CI-only NumPy dependency is locked to the official Windows x64 CPython
3.12 wheel SHA-256 in `requirements-parity.txt`; install it with
`--require-hashes --only-binary=:all:`. It is never a production dependency.

```powershell
ctest --test-dir build/wp-03-5 -C Release --output-on-failure

./core/navigation/verification/run_parity.ps1 `
  -ReplayExecutable ./build/wp-03-5/core/navigation/Release/sih26168_navigation_replay.exe `
  -OutputDirectory ./build/wp-03-5/parity-run-1 `
  -PythonExecutable python

./core/navigation/verification/run_parity.ps1 `
  -ReplayExecutable ./build/wp-03-5/core/navigation/Release/sih26168_navigation_replay.exe `
  -OutputDirectory ./build/wp-03-5/parity-run-2 `
  -PythonExecutable python

python ./core/navigation/verification/python/compare_parity_runs.py `
  ./build/wp-03-5/parity-run-1 `
  ./build/wp-03-5/parity-run-2 `
  ./build/wp-03-5/parity-determinism.json
```

Each parity directory contains full-precision C++ CSV, a machine-readable
summary, line-delimited per-record comparisons, a concise Markdown report, and
a hash manifest. Build/output directories remain ignored and must not be
committed. Passing this bounded synthetic comparison is not real-device drift,
accuracy, or field-validation evidence.
