# WP-11.3 implementation evidence

## Scope and inputs

- Work item: issue #87, frozen GNSS-blackout masking protocol.
- Source snapshot: current `main` at
  `e7a84e5f1307e9b9bb18e6abc5fe525f2c3097dc` was merged into the PR branch on
  2026-10-01. Graph regeneration used the resulting merged source tree at the
  reachable pushed PR head `17b9d4806148b21757f8f7f4d9bc9d7e98fa10d9`.
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
PASS: sanitized Graphify snapshot (3695 nodes, 6112 edges, 244 communities)

python ci/generate_contract_bindings.py --check
PASS: generated contract bindings

python ci/verify_repository.py all
PASS: all

python ci/run_python_checks.py python
python ci/run_python_checks.py dataset
GitHub Selective CI run #177 passed every requested lane on PR head
`17b9d4806148b21757f8f7f4d9bc9d7e98fa10d9`. The provenance-only follow-up
requires a fresh GitHub CI run after it is published; no future result is
represented here as a pass.
```

Dependency-graph regeneration used the repository wrapper with the exact
configured Graphify package version 0.9.53 in an isolated environment:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File tools/graphify/update_graph.ps1
```

Two fresh rebuilds from the same final source tree produced byte-identical
sanitized artifacts. Both `source_parent_commit` and
`raw_graph_built_at_commit` name reachable pushed head
`17b9d4806148b21757f8f7f4d9bc9d7e98fa10d9`, and
`source_includes_working_tree` is false. The repository manifest was then
regenerated from that final snapshot. The verified snapshot contains 3695
nodes, 6112 edges, and 244 communities. Final artifact SHA-256 values:

```text
GRAPH_REPORT.md             38fa3ceb2ce2637da800fe640b9cd686f40c3f2e6fa50edcfadb5fe8963e3250
graph.json                  d0f922c79200f01813723213f1eb17efd32f851028611df4c38a72140d5a9328
metadata.json               f89d4aaa940c8122295376e498634f132605008a0f1c50c92924271ad3ccaf96
SHA256SUMS.txt              e4b10f966f98e3863d94900fde91be12cfc97b2bf606a1911b088b0238fd0db3
repository_manifest.json   a3d3cf65dc0995c1d22f8b1eb76a59a51e2593c077806eabbffccfa91728d966
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
