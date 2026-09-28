# WP-11.1 matched classical baselines

This bounded package implements three deterministic, model-disabled references for
GNSS-blackout evaluation: last-position hold, constant velocity, and constant turn
rate. Every baseline receives the same journey samples and Boolean blackout mask.

The IO-VNBD files remain outside Git. Run a private smoke evaluation with:

```text
python experiments/wp11_1/evaluate.py <V-journey.csv> \
  --output experiments/wp11_1/reports/smoke.json --limit 20000
```

Run the narrow tests with:

```text
python -m unittest discover -s experiments/wp11_1/tests -v
```

Reports are exploratory evidence only. The default periodic blackout schedule is
provisional until WP-11.3 freezes the masking protocol; it must not be used for a
promotion, safety, or release claim.

