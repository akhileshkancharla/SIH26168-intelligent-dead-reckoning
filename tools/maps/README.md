# S6B1 external road-graph verification

WP-08.1 imports only the immutable identity and bounded verification evidence
for the conditionally accepted S6B1 road-graph foundation. The actual PBF,
SQLite graph, exact routes, bundled wheel and delivery ZIP remain in an
external private workspace and must never be copied into Git or CI.

The tracked `s6b1_reference_v1.json` conforms to the Tier-A I-21
`MapGraphManifest` schema. It records source, region, graph, toolchain and
delivery hashes; CRS/bounds; mandatory OpenStreetMap attribution; graph/test
counts; and the unresolved `FIELD_VALIDATION_PENDING` route status. A null
`display_sha256` truthfully records that S6B1 does not contain a PMTiles display
artifact.

## Verify an external delivery

Place only the two original delivery files in an external directory:

- `S6B1_ARTIFACT_MANIFEST_v1.json`
- `S6B1_MGIT_Road_Graph_Foundation_v1.zip`

Then run:

```powershell
python tools/maps/verify_s6b1_artifact.py --artifact-dir <external-directory>
```

Add `--json` for a bounded machine-readable result. The verifier:

1. validates the tracked I-21 reference against its Draft 2020-12 schema and
   requires the S6B1 map-version hash token to match the source PBF SHA-256;
2. hashes the delivery manifest and ZIP using streaming SHA-256;
3. rejects duplicate, encrypted, absolute, traversal or undeclared ZIP members;
4. checks every declared member size and hash without extracting the archive;
5. applies the same map-version/source-hash check to the delivery manifest;
6. cross-checks source/region/graph hashes, exact bounds, attribution, graph
   counts, deterministic rebuild hashes and all recorded test outcomes; and
7. rejects any route that is not still `FIELD_VALIDATION_PENDING` or that is
   represented as finally selected.

The currently frozen delivery is intentionally rejected: its manifest declares
`mgit-pbf-0711df3ca31f3daf-v1`, while the authoritative source PBF SHA-256 begins
`0711df3ca31f3d83`. The tracked canonical identity uses the matching 16-hex
prefix. Do not rewrite the external manifest or archive; a corrected immutable
replacement must come from the artifact producer and will have new delivery
hashes.

Verification failure rejects the map package. Navigation remains unmatched;
the verifier does not alter C-07 state and does not implement graph-store
access, candidate generation or map matching.

## Tests

All tests construct synthetic temporary archives outside the repository:

```powershell
python -m unittest discover -s tools/maps/tests -v
```

The Python CI lane runs these tests in the same clean external environment as
the bootstrap contract tests.
