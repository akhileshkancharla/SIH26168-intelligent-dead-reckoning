# WP-11.3 implementation evidence

## Scope and inputs

- Work item: issue #87, frozen GNSS-blackout masking protocol.
- Source snapshot: current `main` at
  `b3dc2a03447e93ad00f3169f358f89301c4e6c72` was merged into the PR branch on
  2026-10-03. Graph regeneration used the resulting clean merged source tree at
  the reachable pushed PR head `5231f3769ebc998f534a803ed1112aba76bcbb40`.
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
- The standard clean Python CI runner preserves the merged WP-11.1 and WP-11.2
  suites while adding the WP-11.3 training suite.

## Verification

Executed from the repository root with the host Python environment:

```text
python -m unittest discover -s tools/training/tests -v
14 tests passed

python -m unittest discover -s experiments/wp11_1/tests -v
10 tests passed

python -m unittest discover -s experiments/wp11_2/tests -v
6 tests passed

python -m unittest discover -s tools/dataset/tests -v
162 tests passed

python -m unittest discover -s tools/bootstrap/tests -v
73 tests passed; 1 environment-dependent editable-install test skipped

python -m unittest discover -s ci/tests -v
26 tests passed

python tools/graphify/verify_graph.py
PASS: sanitized Graphify snapshot (3760 nodes, 6210 edges, 250 communities)

python ci/generate_contract_bindings.py --check
PASS: generated contract bindings

python ci/verify_repository.py all
PASS: all

python ci/run_python_checks.py python
python ci/run_python_checks.py dataset
GitHub Selective CI run #177 passed every requested lane on the prior reviewed
head. The current conflict-resolution follow-up requires a fresh GitHub CI run
after it is published; no future result is represented here as a pass.
```

Dependency-graph regeneration used the repository wrapper with the exact
configured Graphify package version 0.9.53 in an isolated environment:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File tools/graphify/update_graph.ps1
```

Two fresh rebuilds from the same final source tree produced byte-identical
sanitized artifacts. Both `source_parent_commit` and
`raw_graph_built_at_commit` name reachable pushed head
`5231f3769ebc998f534a803ed1112aba76bcbb40`, and
`source_includes_working_tree` is false. The repository manifest was then
regenerated from that final snapshot. The verified snapshot contains 3760
nodes, 6210 edges, and 250 communities. Final artifact SHA-256 values:

```text
GRAPH_REPORT.md             b9e1e169e5c3734dc8db117043e3a23f72e4f944e63db461c71d061b2829b18d
graph.json                  9be50cd84e4d0eb301396a41d571688097aeabdfa89ec3a99eb70f805457eb80
metadata.json               418b86ace97a99dbe31255b0cfcd63a520ffc9dc29feec2207df8510000231c1
SHA256SUMS.txt              6117713baf45085ac1e89d7669250b94858e5f1e9b8199dfeb9a9a29abc8ecdf
repository_manifest.json   a9073cfbf421c97f8ba3e1f1f07bbb23e38239b1f14202856374845852571bed
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
