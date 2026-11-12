# WP-07.3 host-screening evidence

## Scope and source

- Issue: #63, related to parent #8.
- Base: merged WP-07.2 on `main` at `de942eb4b79d993d4c64441d19e5e13af2c73504`.
- Final source commit for this graph: `a2519c3d0f099db97033ed147e22707f61a34661` (SSH-signed).
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

Current-head review remediation: `FixRejectionScreen::present()` now calls the
WP-07.1 precheck before testing whether a C-07 result is pending. Every nonempty
incoming identity is thereby consumed on first presentation, including a
well-formed fix rejected as `PendingCoreDecision`. Duplicate, malformed and
empty identities retain their precheck reasons. The native regression covers a
busy fix presented again after finalization, and duplicate/malformed/empty
inputs while the first decision is pending.

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
- `gnss-rejection-native`: **not run locally** for the review remediation; this
  host lacks a usable C++20/CMake toolchain. The CMake target is registered for
  current-head CI. No native-test pass is claimed before that job completes.

Graphifyy 0.9.53, code-only extraction with one AST worker, rebuilt twice from
unchanged source and normalized to the same committed source metadata. The four
sanitized artifacts were byte-identical: 4,041 nodes, 6,682 edges, 275
communities. The extractor reported an existing partial-parse warning for
`NativeNavigationBridgeTest.kt`; graph verification passing does not erase
that limitation. `source_includes_working_tree` is false.

Final graph artifact SHA-256 values:

```text
GRAPH_REPORT.md  c812cfedc54ac60f8e990d6ecd0d2f846ab4b17dd856e8d057cc3bea7b8af3a0
SHA256SUMS.txt   eabc56eb0f94e31b721dba3ccf60e01704408d97a9f62385be7c7a0c2c55e3bf
graph.json       8d2e7c4d9547281e9d9cf702da8f034c63cb00d3cbacc7e9cc319dc9a5fea318
metadata.json    7b370628ff89d063e0d8bbd014ef2d0e8f55c29406f5f2a6d9d8aa0375442029
```

Only synthetic fixtures were used. No private source records, model weights,
raw `graphify-out/` data, build outputs, virtual environments, machine-local
paths, credentials, or signing material belong in this change.
