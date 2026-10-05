# WP-07.3 host-screening evidence

## Scope and source

- Issue: #63, related to parent #8.
- Base: merged WP-07.2 on `main` at `de942eb4b79d993d4c64441d19e5e13af2c73504`.
- Final source commit for this graph: `c4d019f2a81b4268b929c1d305a832d3cfe2b8c0` (SSH-signed).
- Inputs: Architecture Revision 3, interfaces I-02/I-12, the accepted C-07
  measurement-status API, synthetic test fixes, and caller-supplied policy
  bounds. The tests use synthetic 40 m/s speed and 25 m horizontal-accuracy
  limits; these are **not** approved operational thresholds.

## Bounded output

`FixRejectionScreen` composes the existing evidence-once GNSS precheck with
reported-accuracy and physical-displacement screening. It forwards an eligible
fix for C-07 consideration but never marks it accepted until the caller reports
the matching C-07 result. Core innovation rejection remains a distinct reason;
this module does not compute NIS or mutate scientific state. Rejected physical
jumps do not become a baseline for later fixes. The caller remains responsible
for binding the reported result to the actual I-12 update; this host component
cannot authenticate a forged callback.

The displacement screen can reject gross jumps but cannot prove a candidate is
unbiased, detect every slowly drifting bias, or replace C-07's innovation gate.
No WP-07.4 reacquisition gate, Android integration, or field-accuracy claim is
included. Runtime use requires separately approved frozen bounds.

## Verification

Local host: Python 3.12.14. Commands were run from the repository root.

- `python ci/verify_repository.py all`: PASS after manifest regeneration.
- `python ci/verify_repository.py forbidden`: PASS.
- `python ci/generate_contract_bindings.py --check`: PASS.
- `python tools/graphify/verify_graph.py`: PASS.
- `git diff --check`: PASS.
- Inherited WP-11.3 masking suite: 14/14 Python tests passed.
- `gnss-rejection-native`: **not run locally**; this host lacks a usable
  C++20/CMake toolchain. The CMake target is registered for current-head CI.
  No native-test pass is claimed before that job completes.

Graphifyy 0.9.53, code-only extraction with one AST worker, rebuilt twice from
unchanged source and normalized to the same committed source metadata. The four
sanitized artifacts were byte-identical: 4,041 nodes, 6,682 edges, 275
communities. The extractor reported an existing partial-parse warning for
`NativeNavigationBridgeTest.kt`; graph verification passing does not erase
that limitation. `source_includes_working_tree` is false.

Final graph artifact SHA-256 values:

```text
GRAPH_REPORT.md  fd56fc14c6a28e75ffa44050221a5c6d2a557ee805a0eaf339ec4ab53ab514eb
SHA256SUMS.txt   fcdb48e19f4111c6b9b5892cae5ff1baab72891223bff5c9e9272fedd5c8c2f2
graph.json       ec89ac9991e1211b1899c5d58b1b8425038fd4c7f48f624c9a7ad0389a3b0fe9
metadata.json    f27005d6a359addb2dcba617d394a1e6e48faa7415dc84d52fe37c5f8b32d403
```

Only synthetic fixtures were used. No private source records, model weights,
raw `graphify-out/` data, build outputs, virtual environments, machine-local
paths, credentials, or signing material belong in this change.
