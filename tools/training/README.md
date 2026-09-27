# Offline training and evaluation tooling

Offline-only ML experiments belong to WP-11. No model training or performance
claim is implemented by the WP-11.3 scope below.

## Frozen GNSS-blackout masking (WP-11.3 / Issue #87)

`blackout_masking.py` implements a deterministic preprocessing boundary for
synthetic or private offline records:

- protocols must be explicitly `FROZEN`, use the declared session monotonic
  clock, contain non-overlapping half-open intervals (`start_ns <= t < end_ns`),
  and declare the exact GNSS fields hidden by each software-simulated outage;
- canonical ordering and compact JSON produce a stable SHA-256 protocol identity
  that experiment evidence can pin;
- source records are never mutated; hidden GNSS values move to a separate
  reference-only view while the inference view retains no configured field;
- no zeroing, interpolation, forward fill, or future-GNSS substitution is
  allowed, and an internal canary re-checks every produced inference record;
- raw/reference preservation is for later evaluation only and is not evidence of
  model quality, navigation accuracy, or runtime integration.

This is an offline C-16 protocol only. C-09 still owns runtime outage and
reacquisition control, and C-07 remains the sole owner of navigation state.

Run the narrow synthetic test suite with:

```text
python -m unittest discover -s tools/training/tests -v
```
