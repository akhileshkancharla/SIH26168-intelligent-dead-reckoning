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
  `ALLOWED`. Neither the real runtime-available feature names nor the
  real IO-VNBD ground-truth label names are known to this repository --
  this repo's own contracts and fixtures contain no frozen enum of
  either, and inventing one would fabricate a fact this repository does
  not have (the same reasoning as `schema_allowlist.py`'s six schema
  names). The shipped `config/feature_firewall.json` is therefore a
  **template** (`status: TEMPLATE_PENDING_REVIEW`) with placeholder
  entries on both sides; `require_active_firewall` refuses to enforce it
  (or any document that still looks like it, checked independently on
  each side) until a human replaces both placeholder lists and sets
  `status: ACTIVE`.

- `private_data_scan.py` — WP-10.6 (Issue #84). A WP-10-scoped
  complement to `ci/verify_repository.py`'s repository-wide `forbidden`
  check: `scan_tree` walks a directory and flags anything that looks
  like it could be real dataset content by mistake -- a `data/`- or
  `private/`-prefixed sub-path at any depth, a raw archive/sensor-data
  file suffix (`.zip`, `.parquet`, `.h5`, ...), or a file over a small
  size ceiling. `assert_tree_is_clean` is the raising variant that
  `tests/test_private_data_exclusion.py` runs against this directory
  itself on every test run.

- `tests/test_leakage_canary.py` — WP-10.6 (Issue #84). End-to-end
  canary scenarios wiring `manifest.py`, `schema_allowlist.py`,
  `grouping.py`, `splits.py` and `feature_firewall.py` together over
  small synthetic datasets: a clean "golden path" scenario that must
  pass every stage, plus deliberate attack scenarios (an out-of-allowlist
  schema hidden in an otherwise-valid manifest, a forbidden label mixed
  into an otherwise-clean feature set, a hand-corrupted overlapping
  split, an orphaned group_id) that must each be rejected by the
  pipeline as a whole, not just by one module in isolation. Also proves
  concretely, using two identifiers chosen because hashing them
  independently would place them in different splits, that grouping
  byte-identical files *before* splitting is what prevents that leak --
  not an accident of these modules' particular hash function.

## Scope boundaries

This directory now has code addressing every WP-10.1 through WP-10.6
sub-issue listed in Issue #11 -- but that is a statement about code
coverage, not about this being a closed, active, or fully-approved
pipeline. As of this revision:

- Issues #79 through #84 (WP-10.1 through WP-10.6) remain open in the
  tracker; none has been reconciled to in-progress/closed status.
- `schema_allowlist.py`'s shipped `config/io_vnbd_schema_allowlist.json`
  (WP-10.2) and `feature_firewall.py`'s shipped
  `config/feature_firewall.json` (WP-10.5) are both still
  `TEMPLATE_PENDING_*` placeholder configuration -- see below. Neither
  can enforce anything against a real feature set or manifest until a
  human replaces the placeholders with real IO-VNBD-derived values and
  sets `status: ACTIVE`.
- `dataset_manifest_v2.schema.json`'s `file_group_ids` field (WP-10.1,
  coordinated from WP-10.3) is now an owner-ratified required I-20
  field, listed in `INTERFACE_SCHEMA_PLAN.md#I-20`'s Required Fields
  as of schema `2.0.0` -- see `ADR-022` in
  `docs/architecture/SIH26168_ADR_Register_v1.md` (formerly tracked as
  OD-18 in `docs/architecture/SIH26168_Open_Decisions_v1.md`, now
  resolved).
- The verification evidence in each PR description is a local
  `python -m unittest` / `ci/verify_repository.py` run, not a green CI
  run on GitHub -- rerun and attach real CI output once available.

See `docs/architecture/SIH26168_High_Level_Architecture_Revision3.md`
(component C-15) and `contracts/INTERFACE_SCHEMA_PLAN.md#I-20` for the
architecture this tooling implements, and each module's own docstring
for what it still does not (and, per `docs/PRIVATE_ARTIFACT_POLICY.md`,
must never) do: read, store, or validate real IO-VNBD bytes. Real
IO-VNBD-specific facts this repository does not have access to -- the
six real schema identifiers (`schema_allowlist.py`), the real
runtime-available feature names and ground-truth label names
(`feature_firewall.py`) -- remain shipped as reviewable
`TEMPLATE_PENDING_*` configuration until a human with
`SIH26168_IO_VNBD_Dataset_Feasibility_Audit_v1.1` and the runtime
feature spec replaces them and sets `status: ACTIVE`.

## Tests

```
python -m unittest discover -s tools/dataset/tests -v
```

Tests run only against the synthetic fixture in `tests/fixtures/` — never
real IO-VNBD data — per the Verification Strategy's "unit tests only on
synthetic/tiny lawful fixtures; no IO-VNBD download" rule.
