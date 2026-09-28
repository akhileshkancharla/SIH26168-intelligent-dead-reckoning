# WP-11.5 exploratory evaluation and promotion recommendation

## Recommendation

**DO NOT PROMOTE.** The supplied evidence is exploratory and does not satisfy the
Architecture Revision 3 model-promotion gates.

## Evidence identity

- Upstream reference: `PR #175 commit a6c525f, experiments/wp11_4/reports/synthetic_ablation.json`
- Upstream report SHA-256: `18b7b5c2518f8ce7ac757c673fd637278c221c38f2341e9342b80f7bcd9fd26a`
- Upstream input SHA-256: `dc7f88ea2b75aa10bf62f4a17081a434a9f64949c0b296fde9216d61d529b41d`
- Dataset manifest SHA-256: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- Split / mask: `synthetic-journey-safe-test-v1` / `synthetic-frozen-blackout-v1`
- Evidence class: `synthetic-fixture`
- Publisher version: `wp11.5-v2`

## Exploratory aggregate metrics

| Variant | Kind | RMSE (m) | p95 (m) | Endpoint (m) |
| --- | --- | ---: | ---: | ---: |
| `constant_velocity` | baseline | 4.082483 | 5.000000 | 5.000000 |
| `ridge_full` | model | 3.109126 | 4.000000 | 4.000000 |
| `ridge_without_speed` | feature_ablation | 3.593976 | 4.500000 | 4.500000 |

These values describe only the supplied aggregate evidence and are not a field claim.

## Gate findings

- Input identifiers mark the evidence as a synthetic fixture.
- Upstream scientific status is exploratory-not-promoted.
- No S4 completion or approved promotion-threshold evidence is present.
- No model-package, runtime parity, latency, or device evidence is present.

## Claim boundary

Permitted:
- The publication pipeline deterministically summarized the supplied aggregate fixture.
- The current evidence is insufficient for model promotion.

Prohibited:
- real-world performance
- production readiness
- model promotion
- safety or field validity

## Upstream limitations

- This report compares supplied matched error traces; it does not validate upstream model training.
- Results are exploratory and are not a model-promotion or safety claim.
- Raw private data and per-sample coordinates must remain outside Git.
