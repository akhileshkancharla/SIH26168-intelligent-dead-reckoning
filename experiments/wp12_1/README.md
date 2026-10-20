# WP-12.1 — fail-closed ONNX candidate export

This directory contains the reviewable export boundary for issue #90. It exports an approved learned-model candidate to ONNX and emits a provenance manifest. It intentionally does **not** train a model or manufacture a candidate.

## Current status

PR #176 is merged, but its committed recommendation is `do-not-promote`, with `exploratory-only` scientific status and synthetic-fixture evidence. Therefore this branch does not commit an ONNX model, model weights, or promotion claims. Supplying the current recommendation to the exporter is rejected before model code is imported or artifacts are written.

A real export becomes possible only when an authorized promotion document identifies the same candidate and records:

- `recommendation: "promote"`;
- `scientific_status: "promotion-approved"` or `"candidate-approved"`;
- a non-synthetic evidence class.

## Usage

Run this only in the approved private model workspace that contains the candidate weights and model factory:

```bash
python experiments/wp12_1/export_candidate.py \
  --candidate candidate_descriptor.json \
  --promotion promotion_recommendation.json \
  --output-dir dist/wp12_1_candidate
```

The private export environment must pin compatible versions of `torch` and `onnx`. They are deliberately not added to the repository's general runtime dependencies because the repository does not currently contain an approved model package.

Example candidate descriptor:

```json
{
  "schema_version": 1,
  "candidate_id": "approved-candidate-id",
  "model_factory": "private_model_package.factory:build_model",
  "state_dict": "artifacts/approved-candidate.pt",
  "opset_version": 17,
  "inputs": [
    {
      "name": "imu_window",
      "shape": [1, 100, 6],
      "dtype": "float32"
    }
  ],
  "outputs": ["displacement"],
  "runtime_min": "python-runtime-version",
  "input_contract": "documented feature ordering and units",
  "window": "100 samples",
  "normalization": "training normalization identifier",
  "bounds": "documented output bounds",
  "training_run": "immutable training-run identifier",
  "dataset_manifest": "immutable dataset-manifest identifier",
  "metrics": {
    "held_out_metric": 0.0
  },
  "redistribution_status": "private; redistribution approval required"
}
```

The model factory must accept no arguments and return the exact architecture expected by the state dictionary. Input shapes must use positive fixed dimensions. The exporter loads weights with `weights_only=True`, performs a strict state-dictionary load, invokes `model.eval()`, exports with explicit input/output names, and runs `onnx.checker`.

## Outputs

A successful run creates a new output directory containing:

- `model.onnx`;
- `model_manifest.json`, including the ONNX SHA-256, candidate and promotion document SHA-256 values, opset, input/output contracts, metrics, provenance, and redistribution status.

The exporter refuses to overwrite an existing output directory. Keep private weights, raw datasets, and unauthorized model artifacts out of Git. Distribution of the ONNX file remains subject to the recorded redistribution status.

## Verification note

No tests were run for this change, per the explicit submission instruction. The pull request must not be interpreted as evidence that an actual model has been exported or validated; that remains gated on a promotion-approved real candidate.
