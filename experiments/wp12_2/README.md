# WP-12.2 — ONNX golden tensor generation

This directory contains the reviewable golden-vector boundary for issue #91. It verifies a WP-12.1 ONNX bundle, executes it with immutable real input tensors, and publishes input/output `.npy` files plus a provenance manifest.

It does not train, promote, or manufacture a model. The merged WP-12.1 dependency deliberately contains no ONNX artifact because its upstream recommendation remains `do-not-promote`, `exploratory-only`, and `synthetic-fixture`. Consequently, no golden tensors are committed by this work package.

## Required private inputs

Generation is allowed only in the approved private workspace with:

- a WP-12.1 bundle containing `model.onnx` and `model_manifest.json`;
- a request descriptor naming the same immutable model;
- one hash-pinned `.npy` file for every ONNX input;
- pinned compatible versions of NumPy and ONNX Runtime.

Example request:

```json
{
  "schema_version": 1,
  "model_id": "approved-model-id",
  "source_evidence": "immutable-private-fixture-id",
  "inputs": [
    {
      "name": "imu_window",
      "file": "fixtures/imu_window.npy",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    }
  ]
}
```

Run:

```bash
python experiments/wp12_2/generate_golden.py \
  --bundle private/wp12_1_bundle \
  --request private/golden_request.json \
  --output-dir dist/wp12_2_golden
```

## Fail-closed checks

Before inference, the generator requires:

- the model bytes to match the I-19 manifest hash;
- the request model ID to match the manifest;
- request input names to exactly match ONNX inputs;
- input files to match their declared SHA-256;
- fixed positive tensor shapes and supported scalar dtypes;
- finite floating-point input values;
- ONNX output names and order to match the manifest.

The session uses only `CPUExecutionProvider` and disables graph optimizations for a conservative reference path. Every returned output must match the ONNX dtype and fixed shape and contain only finite floating-point values.

## Output

A successful run atomically creates a new directory containing numbered input and output `.npy` files and `golden_manifest.json`. The manifest records model, candidate, promotion, request, runtime, provider, tensor shape/dtype, and per-file hashes. Existing destinations are refused and failed staging directories are removed.

These files are parity evidence for the exact model/runtime/input combination only. They do not prove navigation accuracy, Android latency, OOD handling, or authorization to redistribute a private model or dataset.
