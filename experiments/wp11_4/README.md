# WP-11.4 matched baseline, model and feature ablations

This bounded experiment harness compares error traces produced by the approved
WP-11 baseline, training and frozen-mask stages. It deliberately does **not**
build a new model, invent a split, or define a blackout protocol.

The input JSON must identify one immutable `dataset_manifest_sha256`, one
journey-safe `split_id`, one frozen `mask_id`, and a set of variants containing:

- at least one classical `baseline`;
- exactly one full `model`; and
- at least one `feature_ablation` with explicit `omitted_features`.

Every variant must provide the identical ordered `sample_ids`, a matching
`errors_m` array, and the SHA-256 digest of its immutable upstream evidence.
The harness fails closed if samples differ, IDs repeat, values are
missing/non-finite, provenance is malformed, or any required comparison class is absent. It computes
mean, RMSE, p95, maximum and endpoint errors and records RMSE deltas against the
best classical baseline and the full model.

Reports use one canonical byte representation: sorted, indented UTF-8 JSON with
a single trailing LF. This keeps the artifact SHA-256 identical across Windows,
Linux and macOS checkouts.

Run it with:

```text
python experiments/wp11_4/ablation.py evidence.json \
  --output experiments/wp11_4/reports/ablation.json
```

Run the focused tests with:

```text
python -m unittest discover -s experiments/wp11_4/tests -v
```

Only hash/provenance metadata and bounded aggregate reports may be committed.
Raw IO-VNBD data, per-sample coordinates and other private source material must
remain in the approved private workspace. Every report is exploratory and must
not be represented as model promotion, production readiness or a safety claim.
