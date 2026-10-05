# WP-11.5 exploratory publication

This package turns a validated WP-11.4 aggregate report into a deterministic,
reviewable evaluation publication. It does not train a model, read private raw
data, set promotion thresholds, export a model, or authorize runtime use.

The publisher fails closed. Its current input contract contains exploratory
aggregate evidence but no S4 completion, approved threshold, redistribution,
model-package, runtime-parity, latency, or device evidence. Consequently its
only valid recommendation is `do-not-promote`.

This PR is stacked on the WP-11.4 branch from PR #175. The committed fixture is
byte-identical to `experiments/wp11_4/reports/synthetic_ablation.json` at
SHA-256 `18b7b5c2518f8ce7ac757c673fd637278c221c38f2341e9342b80f7bcd9fd26a`.
Generated JSON and Markdown use explicit UTF-8 with LF line endings so their
artifact hashes remain stable across platforms.

Run the synthetic publication with:

```text
python experiments/wp11_5/publish.py \
  experiments/wp11_5/fixtures/synthetic_ablation.json \
  --upstream-reference "PR #175 commit a6c525f, experiments/wp11_4/reports/synthetic_ablation.json" \
  --output-json experiments/wp11_5/reports/promotion_recommendation.json \
  --output-markdown experiments/wp11_5/reports/promotion_recommendation.md
```

Run the focused tests with:

```text
python -m unittest discover -s experiments/wp11_5/tests -v
```

The committed fixture and publication are synthetic. They prove deterministic
publication and honest gate handling only; they make no performance, safety,
field-validity, production-readiness, or model-promotion claim.
