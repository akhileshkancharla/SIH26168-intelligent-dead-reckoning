# WP-10 private dataset tooling

Implements the parts of **WP-10 (Private IO-VNBD ingestion and leakage
firewall, Issue #11 / component C-15)** that this repository is allowed to
contain: schema, hashing and structural-integrity tooling. It never stores,
downloads or reads real IO-VNBD bytes, and no tool in this directory writes
anything under the repository's own working tree — see
`docs/PRIVATE_ARTIFACT_POLICY.md` and `ci/verify_repository.py`'s
`forbidden` check, which flags any on-disk `private/`- or `data/`-prefixed
path under the repo root regardless of Git tracking status.

## Modules

- `manifest.py` — WP-10.1 (Issue #79). Builds, loads and validates
  `DatasetManifest` (I-20) documents against
  `contracts/schemas/dataset_manifest_v2.schema.json`, and verifies that a
  manifest's recorded SHA-256 hashes still match the files it describes
  (`verify_file_hashes`). A `DatasetManifest` is hash-only and safe to
  commit to Git; the files it describes are not.
- `workspace.py` — WP-10.1 (Issue #79). Decides where the private,
  offline dataset workspace lives (always **outside** this repository
  checkout — see `assert_outside_repository`/`WorkspaceLocationError`) and
  creates its `archives/`, `extracted/` and `manifests/` sub-directories.
  Defaults to a sibling directory of the repo checkout
  (`../sih26168-private-data`); override with the
  `SIH26168_PRIVATE_DATA_ROOT` environment variable.

## Scope boundaries

This directory intentionally does **not** yet implement:

- the six-schema IO-VNBD validation allowlist (WP-10.2 / Issue #80)
- duplicate/parent-session grouping (WP-10.3 / Issue #81)
- leakage-safe split construction (WP-10.4 / Issue #82)
- the runtime-feature/forbidden-label firewall (WP-10.5 / Issue #83)
- leakage canary and private-data exclusion tests (WP-10.6 / Issue #84)

Each is its own bounded work package; see `docs/architecture/SIH26168_High_Level_Architecture_Revision3.md`
(component C-15) and `contracts/INTERFACE_SCHEMA_PLAN.md#I-20`.

## Tests

```
python -m unittest discover -s tools/dataset/tests -v
```

Tests run only against the synthetic fixture in `tests/fixtures/` — never
real IO-VNBD data — per the Verification Strategy's "unit tests only on
synthetic/tiny lawful fixtures; no IO-VNBD download" rule.
