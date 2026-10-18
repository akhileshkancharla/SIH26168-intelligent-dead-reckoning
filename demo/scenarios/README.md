# Frozen ten-event synthetic scenario and evidence plan

Relates to #16 and #106. [The versioned plan](ten_event_synthetic_evidence_plan_v1.json) freezes the exact user-selected canonical S1 fixture, approved storyboard and demo architecture by file SHA-256, plus all ten semantic events and evidence/interface requirements. It is a planning artifact, not a C-20 runtime contract, COMPLETE I-18 session, executable mask schedule or completed scientific run.

The six-record fixture validates synthetic I-01/I-02 contracts. It is grouped per stream, lacks complete session metadata, and includes global source-time regressions; normal replay eligibility is explicitly false. No event epochs, mask interval, output-rate distribution, state/covariance, candidate scores, NIS, dwell, accepted update or error metric is fabricated. Preserve the original fixture and its ordering. A separately reviewed eligible runtime input is required for playback/integration.

## Frozen inputs

- [Canonical S1 fixture](../../contracts/fixtures/s1_acquisition_round_trip_v1_fixture.json): `44068a9b5beeade2581a7914707596e5b88b6d85cdcec5f9016752908728f2bb`.
- [Approved storyboard](../../docs/architecture/SIH26168_WP15_7_Demo_Narrative_Storyboard_v1.md): `fe5042fece38d3197b3927042f91aae24f5aaeac7e6b7584edca256f80137a49`.
- [Demo architecture](../../docs/architecture/SIH26168_Demo_Architecture_v1.md): `6fba94a27371d1d1b8adc87488eac4474441d84bb71ba872a05ef54300fd4cfa`.

The plan defines persistent replay/source/demo labels, conditional outage/map attribution, scientific/display/reference separation, and unavailable-state behavior. The ten events retain the authoritative order: anchor, software outage, output continuity, inertial propagation, turn, uncertainty, candidates, biased-return rejection, credible return, and smooth display recovery/comparison. Narrative event order does not supply missing scientific observations or timing.

## Verification and handoff

Verify every input file hash and Event 1–10 order before reuse. The existing S1 fixture round-trip and focused inventory tests validate only their declared synthetic scope. Run `python tools/acquisition/s1_fixture_roundtrip.py`, `python -m unittest ci.tests.test_s1_reduced_import_inventory tools.bootstrap.tests.test_s1_fixture_round_trip`, and `python ci/verify_repository.py all` with the declared Python dependencies. Exact-head results are recorded in the PR. The JSON is authored configuration/evidence planning; no raw recording, binary model or generated scientific result is included.

WP-15.2 must reject this input as normal playback rather than silently repair it. WP-15.3–WP-15.5 require real integrated outputs for their event evidence, and WP-15.6/WP-15.11 must stop an executed-rehearsal claim at the preflight gate. A synthetic desk review may use this frozen plan while recording every unavailable capability and blocker. WP-15.10 recording and Issue #77 device/airplane-mode proof remain separate. Any future executable scenario/input replaces nothing silently: version it, record new hashes/provenance/configuration, and obtain designated review. This freeze is prepared for review and does not close the parent or child issue.

Attribution: canonical fixture and existing approved storyboard/Demo Architecture; plan prepared with Codex assistance. Retain MapLibre/content credits and full OpenStreetMap attribution in map-bearing footage.
