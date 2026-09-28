# WP-11.3 implementation evidence

## Scope and inputs

- Work item: issue #87, frozen GNSS-blackout masking protocol.
- Source snapshot: the PR branch was updated from current `main` through the
  authenticated repository UI on 2026-09-28 before the review fix was applied.
- Governing inputs: Architecture Revision 3; Development Design Baseline;
  interfaces I-14, I-20, and I-22; the active WP-10 runtime-feature firewall;
  and the issue acceptance boundary.
- Data: synthetic records only. No private paths, bytes, identifiers, or result
  values were used or committed.

## Implemented output

- `blackout_masking.py` freezes non-overlapping software-simulated intervals
  into a canonical SHA-256 identity.
- Masking uses half-open intervals and produces separate immutable inference
  and reference views without mutating raw input.
- Configured GNSS fields are removed, never zeroed, interpolated, or
  forward-filled, and a defense-in-depth canary checks every masked result.
- Hidden fields are restricted to the measurement members of the authoritative
  I-02 `LocationGnssFixV1` contract; IMU, target/label, metadata, unprefixed,
  and unknown names fail closed before protocol hashing.
- Protocol, record, clock, ordering, duplicate identity, finite-value, and hash
  mismatches fail closed.
- The standard clean Python CI runner now discovers the training tests.

## Verification

Executed from the repository root with the host Python environment:

```text
python -m unittest discover -s tools/training/tests -v
14 tests passed

python -m unittest discover -s tools/dataset/tests -v
162 tests passed

python -m unittest discover -s tools/bootstrap/tests -v
65 tests passed; 1 environment-dependent editable-install test skipped

python -m unittest discover -s ci/tests -v
passed

python ci/run_python_checks.py python
the prior head passed in a fresh external virtual environment; the current
host rerun stalled while installing build dependencies, so GitHub CI remains
authoritative for the updated head and this rerun is not represented as a pass
```

Dependency-graph regeneration was attempted with the repository wrapper:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File tools/graphify/update_graph.ps1
```

It could not start because the required `graphify` executable/package version
0.9.53 is not installed in this environment. Per repository policy, the tool
was not installed ad hoc and this limitation is not represented as a pass. The
previous sanitized snapshot remains unchanged.

The conservative CI selector requests every lane because the shared Python test
runner changed. Native and Android builds were not converted into local passes:
this host has JDK 17, but neither CMake/CTest nor Gradle is installed on `PATH`.
Those unchanged build lanes remain for the repository's provisioned Windows CI
runner. The WP-11.3 implementation and tests are Python-only.

## Evidence limits

This output proves deterministic synthetic masking behavior only. It does not
train a model, compute metrics, validate private data, implement runtime C-09
outage control, modify C-07 navigation state, prove Android/ONNX integration,
or support any navigation-accuracy or field-validation claim.
