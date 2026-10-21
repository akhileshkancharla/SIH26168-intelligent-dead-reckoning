# WP-12.3 — ONNX Runtime Mobile integration

This Android integration implements the bounded C-17/I-19 mobile runtime boundary for issue #92. It pins the official ONNX Runtime Android AAR and provides a fail-closed Kotlin adapter for a separately approved model bundle.

No ONNX model, private fixture, golden tensor, or scientific result is committed.

## Runtime identity

- Maven coordinate: `com.microsoft.onnxruntime:onnxruntime-android:1.31.0`
- Execution provider: default CPU provider only; this integration does not opt into NNAPI, XNNPACK, QNN, or another accelerator.
- Supported tensor boundary: fixed-shape finite `float32` inputs and outputs.
- Model size ceiling: 32 MiB.
- Model source: caller-supplied bytes from an approved private-device bundle; no network download or asset discovery.

## Fail-closed load gate

`OnnxRuntimeMobile.load` rejects the bundle before session use unless:

- I-19 schema version, model ID, ONNX format, lowercase SHA-256, and semantic minimum runtime are valid;
- the exact model bytes match the approved SHA-256;
- redistribution status is exactly `redistribution-approved` or `private-device-approved`;
- the ONNX opset is in the WP-12 allowlist (13 through 21);
- every input/output name is unique and every shape is fixed and positive;
- the supplied WP-12.2 golden vector matches a code-pinned trusted golden-manifest digest;
- the upstream model-manifest digest, candidate/promotion identities, tensor artifact digests, and canonical decoded tensor payload digests all match that trusted approval;
- the installed native runtime meets the declared minimum;
- runtime input/output names, order, shapes, and `float32` types exactly match the contract;
- an initialization inference matches every approved golden output within an absolute tolerance of `1e-5`.

A missing, unpinned, malformed, mismatched, tampered, or numerically divergent golden vector rejects the bundle before it can become ready. The production trusted-approval map is deliberately empty because no approved private WP-12.2 bundle exists; enabling a model therefore requires a reviewed source change that pins its immutable evidence digests. A rejected bundle returns a typed model-disabled result and never falls back to another model.

## Inference gate

Each call requires the exact approved input-name set, exact shapes and element counts, native-order float buffers, and finite values. Outputs are requested by approved name and revalidated for type, shape, and finiteness before publication. Any exception or mismatch returns model-disabled without presenting the result as navigation evidence.

## Evidence boundary

WP-12.1 and WP-12.2 intentionally committed no model because the available upstream evidence was `do-not-promote`, `exploratory-only`, and `synthetic-fixture`. This integration therefore proves only that the mobile runtime boundary is reviewable. Real device loading, latency, golden parity, navigation benefit, and redistribution authorization remain unclaimed until an approved private bundle and device evidence exist.
