# WP-11.3 implementation evidence

## Scope and inputs

- Work item: issue #87, frozen GNSS-blackout masking protocol.
- Source snapshot: current `main` at
  `5c5e0b9ce5cc419735612b682a7b26bfe36eb1ee` was merged into the PR branch.
  Graph regeneration used the resulting clean merged source tree at reachable
  pushed PR head `f5ec1203144a40588aa38270fa462ae51f3686f0`.
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
PASS: sanitized Graphify snapshot (3900 nodes, 6422 edges, 268 communities)

python ci/generate_contract_bindings.py --check
PASS: generated contract bindings

python ci/verify_repository.py all
PASS: all

The current manifest/evidence follow-up does not claim a new local test run.
Publishing it requests a fresh current-head GitHub CI run.
```

Dependency-graph regeneration used the repository wrapper with the exact
configured Graphify package version 0.9.53 in an isolated environment:

```text
powershell -NoProfile -ExecutionPolicy Bypass -File tools/graphify/update_graph.ps1
```

Two fresh rebuilds from the same final source tree produced byte-identical
sanitized artifacts. Both `source_parent_commit` and
`raw_graph_built_at_commit` name reachable pushed head
`f5ec1203144a40588aa38270fa462ae51f3686f0`, and
`source_includes_working_tree` is false. The repository manifest was then
regenerated after the graph snapshot was committed. The verified snapshot
contains 3900 nodes, 6422 edges, and 268 communities. Final artifact SHA-256
values:

```text
GRAPH_REPORT.md             2ac0d0bccb1a0b11217f92595abfc8456f851269db885e53f1bfd72e823ca290
graph.json                  d1d8a71b125a3633088bfacbae153e6e3e92c71afdbf90e94354daf313c79deb
metadata.json               ded3ea52d321958543627f09acea5a60a68b1ba37454de596d5ed89d3222dda5
SHA256SUMS.txt              70a1c22a639d8de0e4b30221fb87d92fa32f6345d833a205acc3ec869026e7ca
repository_manifest.json   9449fbbacd3959c79754d385acd15fdea493f7583400163516e8b4178b5fd534
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
