# WP-12.2 evidence record

## Dependency state

- Base dependency: merged PR #200 (WP-12.1).
- WP-12.1 outcome: fail-closed ONNX exporter and I-19 manifest contract.
- Upstream scientific recommendation: `do-not-promote`.
- Upstream scientific status: `exploratory-only`.
- Upstream evidence class: `synthetic-fixture`.
- Promotion-approved ONNX bundle available in this repository: no.
- Real immutable input tensor fixture available in this repository: no.

## Reviewable result

The deliverable is a guarded generator for immutable ONNX golden input/output tensors. It verifies the model and every source tensor by SHA-256, enforces exact ONNX names, dtypes, and fixed shapes, rejects non-finite values, runs a CPU-only reference session, and atomically publishes tensors with a canonical provenance manifest.

No model, private fixture, generated tensor, or parity claim is committed. Producing such artifacts without a promotion-approved model and authorized real fixture would fabricate evidence and violate the issue boundary.

## Self-review boundary

The source was reviewed for:

- model-manifest and request schema/type validation;
- duplicate JSON key rejection;
- model, request, and tensor identity binding;
- exact runtime input/output contract matching;
- fixed shape, supported dtype, and finite-value enforcement;
- CPU-only reference execution;
- per-file and source-document hashes;
- refusal of existing destinations;
- staging cleanup and atomic publication;
- preservation of redistribution status;
- absence of model weights, ONNX bytes, private data, and invented results.

## Verification status

Focused regression tests are included and registered in the Python CI. They cover missing/tampered bundles, malformed hashes, duplicate inputs, tampered fixtures, destination refusal, runtime failure cleanup, and a mocked successful publication.

Per the explicit execution instruction for this submission, no tests or repository scans were run locally. GitHub CI and independent review remain required gates. This record does not claim that a real ONNX model or golden parity has been executed.
