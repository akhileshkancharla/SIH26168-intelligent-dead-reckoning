# WP-12.3 evidence record

## Inputs and identity

- Architecture component: C-17 Model packaging validator.
- Interface: I-19 ModelManifest.
- Android runtime artifact: `com.microsoft.onnxruntime:onnxruntime-android:1.31.0`.
- Upstream code dependency: merged WP-12.2 / PR #201.
- Promotion-approved model available in the repository: no.
- Authorized real golden tensor bundle available in the repository: no.

## Reviewable output

- `android/app/src/main/java/org/sih26168/app/model/OnnxRuntimeMobile.kt`
  - validates model identity, rights, runtime minimum, the WP-12 opset allowlist, tensor names/order/types/shapes, and finite values;
  - requires a WP-12.2 golden vector bound to a code-pinned golden-manifest approval;
  - cross-checks the upstream model-manifest, complete deterministic I-19 contract, candidate/promotion, tensor-artifact, and canonical decoded-payload digests;
  - rejects independent mutations to rights, opset, runtime minimum, normalization, bounds, provenance, metrics, or ordered tensor contracts;
  - runs initialization parity and rejects any output exceeding the absolute `1e-5` tolerance;
  - uses native-order direct float buffers;
  - returns typed model-disabled states on every rejected or unavailable path;
  - owns and closes ONNX sessions, options, input tensors, and output results.
- `android/app/src/test/java/org/sih26168/app/model/OnnxRuntimeMobileTest.kt`
  - covers the dependency-free static contract gate, opset allowlist, golden identity/parity checks, complete-contract mutations, and semantic version comparison.
- `android/app/build.gradle.kts`
  - pins the official Android AAR at version 1.31.0.

## Limitations

The production trusted-approval map is deliberately empty because no approved private bundle exists, so the runtime remains model-disabled until immutable bundle digests are pinned by review. No model or real golden vector is bundled, so this change does not claim successful session creation, device inference, latency, memory, battery, thermal behavior, observed golden parity, navigation accuracy, or scientific promotion. Accelerator execution providers are deliberately outside this issue.

## Verification status

The focused tests are included for independent CI/reviewer execution. Per the explicit instruction for this work, no tests or repository-policy scans were run by the implementation agent. This is not recorded as a pass.
