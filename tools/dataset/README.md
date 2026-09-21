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
- `schema_allowlist.py` — WP-10.2 (Issue #80). Enforcement engine for the
  six-schema IO-VNBD validation allowlist: `require_active_allowlist`,
  `classify_schemas`, `enforce_manifest_against_allowlist`. The shipped
  `config/io_vnbd_schema_allowlist.json` is `ACTIVE` with the six structural
  identifiers transcribed from the accepted S0 audit and its 144-row schema
  register. `SCHEMA_INVENTORY.md` records sanitized hashes and the audited
  source revision. This activation does not grant dataset rights or claim an
  S0 pass; private bytes and paths remain outside Git.

- `grouping.py` — WP-10.3 (Issue #81). Deterministic duplicate and
  parent-session grouping: `compute_groups` unions files that are
  byte-identical (same SHA-256) or that declare the same
  `parent_session_id` into one `group_id` (via union-find, so the merge
  is transitive), so WP-10.4's split construction can guarantee zero
  overlap between train/validation/test at the group level.
  `duplicate_members_by_group` reports which groups contain an exact
  duplicate, for audit evidence.

  Group IDs hash a compact JSON array of sorted unique member identifiers,
  preserving boundaries even when identifiers contain control characters.
  This replaces the earlier unit-separator encoding and changes generated
  IDs for existing groups. Regenerate `group_ids`, `file_group_ids`, and all
  derived splits together from the original file/session records under a new
  manifest revision; never combine old and regenerated IDs or overwrite an
  immutable manifest. Downstream training runs must reference that new
  manifest and its regenerated splits.

- `splits.py` — WP-10.4 (Issue #82). Leakage-safe grouped dataset
  splits: `assign_splits` deterministically buckets each `group_id`
  (from `grouping.py`) into train/validation/test by a stable hash of
  the group_id itself -- so a group's split assignment never depends on
  which other groups are present, and adding new groups later never
  reshuffles existing ones. `validate_splits_are_disjoint` and
  `validate_splits_cover_groups` are defense-in-depth checks for
  externally-constructed splits dictionaries.

- `feature_firewall.py` — WP-10.5 (Issue #83). Deny-by-default
  enforcement of the runtime-feature/forbidden-label split: `classify_feature`
  and `audit_feature_set` label each proposed feature name as
  `ALLOWED`, `FORBIDDEN_LABEL` (a ground-truth-only field such as a
  vehicle CAN/telemetry label or precise reference position), or
  `NOT_RUNTIME_AVAILABLE`; `enforce_feature_set` raises on anything but
  `ALLOWED`. The shipped configuration is `ACTIVE` with the frozen
  nine-channel phone-IMU profile and all 29 audited `V29_MAIN` fields as
  forbidden runtime inputs. `FEATURE_CONTRACT_PROPOSAL.md` records the exact
  mapping, evidence hashes, and remaining rights/extractor gates.

## Scope boundaries

This directory intentionally does **not** yet implement:

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
