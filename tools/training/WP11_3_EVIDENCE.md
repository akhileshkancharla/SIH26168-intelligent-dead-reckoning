# WP-11.3 implementation evidence

## Scope and inputs

- Work item: issue #87, frozen GNSS-blackout masking protocol.
- Source snapshot: the PR branch was updated from current `main` through the
  authenticated repository UI on 2026-09-30. Graph regeneration used exact
  head `b2a7fb51f68fd30ab886d8720263d454bea266d5` plus the final runner change.
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
- The standard clean Python CI runner discovers both the merged WP-11.1
  baseline suite and the WP-11.3 training suite.

## Verification

Executed from the repository root with the host Python environment:

```text
python -m unittest discover -s tools/training/tests -v
14 tests passed

python -m unittest discover -s experiments/wp11_1/tests -v
10 tests passed

python -m unittest discover -s tools/dataset/tests -v
162 tests passed

python -m unittest discover -s tools/bootstrap/tests -v
73 tests passed; 1 environment-dependent editable-install test skipped

python -m unittest discover -s ci/tests -v
26 tests passed

python tools/graphify/verify_graph.py
PASS: sanitized Graphify snapshot (3532 nodes, 5802 edges, 232 communities)

python ci/generate_contract_bindings.py --check
PASS: generated contract bindings

python ci/verify_repository.py all
PASS: all

python ci/run_python_checks.py python
python ci/run_python_checks.py dataset
both current-head clean-runner attempts stalled while installing temporary
build dependencies; GitHub CI remains authoritative for these two isolated
runs, and neither attempt is represented as a pass
```

Dependency-graph regeneration used the repository wrapper with the exact
configured Graphify package version 0.9.53 in an isolated environment:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File tools/graphify/update_graph.ps1
```

Two fresh rebuilds from the same final source tree produced byte-identical
sanitized artifacts and repository manifest. The verified snapshot contains
3532 nodes, 5802 edges, and 232 communities. Final artifact SHA-256 values:

```text
GRAPH_REPORT.md             5c0c25fa73290ad9f49884b46ec9100b98f8044c3b77559ecb15fa4051f417eb
graph.json                  d840d5c2763fa2fd88c3929c5085bea72aba071340d63b61e88c722da4c08c2f
metadata.json               53eb1b4fb72cc7c6a1fe668bc39974fbd0b4e570b90bf1efa5de2f34e75b59a5
SHA256SUMS.txt              4caabc0d03e72bf31e72a43388422294f840f2677c1dd5b6718eb506d04ce278
repository_manifest.json   6be816bf8f64cb101748d0a4cc6528454280dc180d9a801eff154c48d6935bdc
```

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
