# WP-12.1 evidence record

## Dependency state

- Base commit: `7124a5bd270cb957226a8d7197c6bb89b7cd3ec7`.
- Dependency PR: #176, merged.
- Promotion source: `experiments/wp11_5/reports/promotion_recommendation.json`.
- Recorded recommendation: `do-not-promote`.
- Recorded scientific status: `exploratory-only`.
- Recorded evidence class: `synthetic-fixture`.

## Result

The reviewable deliverable is a fail-closed export tool and its documented candidate contract. No learned-model weights or ONNX artifact are committed because the dependency evidence does not authorize promotion and does not provide a real candidate model package.

When invoked with the currently committed recommendation, the exporter rejects the request before importing candidate model code, loading weights, or writing output artifacts. A successful future export must retain the immutable candidate and promotion document digests in `model_manifest.json`.

## Self-review record

The implementation was reviewed against these boundaries:

- promotion is explicit and candidate-specific;
- only explicitly allowlisted real-world evidence classes can authorize export;
- every I-19 manifest field is type- and content-validated before model code is imported;
- the state dictionary is loaded in weights-only, strict mode;
- inference export uses evaluation mode and explicit I/O names;
- the generated ONNX graph is checked before success is reported;
- non-finite metric values and malformed or duplicate JSON keys are rejected;
- output names are normalized before uniqueness is checked;
- existing artifact directories are rejected and publication is atomic;
- provenance and redistribution status are carried into the manifest;
- no private weights, raw data, or fabricated results are committed.

## Verification status

The focused exporter suite is registered in the repository Python CI. It verifies the fail-closed boundary without requiring private weights, PyTorch, or ONNX. CI results and reviewer feedback remain independent gates. This record does not claim that an actual candidate model or generated ONNX artifact has passed validation.
