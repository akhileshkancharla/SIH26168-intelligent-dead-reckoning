# WP-11.5 exploratory publication

This package turns a validated WP-11.4 aggregate report into a deterministic,
reviewable evaluation publication. It does not train a model, read private raw
data, set promotion thresholds, export a model, or authorize runtime use.

The publisher fails closed. Its current input contract contains exploratory
aggregate evidence but no S4 completion, approved threshold, redistribution,
model-package, runtime-parity, latency, or device evidence. Consequently its
only valid recommendation is `do-not-promote`.

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
