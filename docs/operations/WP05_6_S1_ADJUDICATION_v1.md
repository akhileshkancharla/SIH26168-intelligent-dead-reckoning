# WP-05.6 S1 evidence-bounded adjudication v1

Relates to #6 and #54. Adjudication record prepared 2026-10-18 IST for the designated reviewers; this is not self-approval or an authorized scientific-gate closure.

**Verdict: `S1-PENDING-DEVICE-EVIDENCE`.** The available synthetic evidence verifies bounded contract behavior. It does not establish the predeclared physical-device gate. The parent physical protocol remains open.

## Evidence examined

| Evidence | Immutable identity / observed outcome | Permitted inference |
| --- | --- | --- |
| [Canonical S1 fixture](../../contracts/fixtures/s1_acquisition_round_trip_v1_fixture.json) | Exact file SHA-256 `44068a9b5beeade2581a7914707596e5b88b6d85cdcec5f9016752908728f2bb`; six records; four I-01/two I-02; explicitly synthetic | A public contract example, not physical telemetry. |
| Existing round-trip harness | `PASS: S1 fixture round-trip records=6 i01=4 i02=2 sha256=869838c689b93b9af69dd29b51b83db803d3acb15bb05f857e1542ff96d57446` | Schema, envelope/payload coherence, finite values, field masks, evidence identity, per-stream order and lossless canonical round-trip pass. Canonical hash is not the file-byte hash. |
| Existing inventory/round-trip tests | 21 tests passed on Python 3.13.2 with jsonschema 4.23.0/referencing 0.35.1 | Synthetic regression and imported-inventory integrity coverage. |
| [WP-05.5 analysis](https://github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning/blob/f87ecae383267c92cc2a78175bbb6115b8e7ce82/docs/operations/WP05_5_SYNTHETIC_S1_ANALYSIS_v1.md) | Immutable report commit `f87ecae383267c92cc2a78175bbb6115b8e7ce82`; PR #194 | Two samples/one interval per stream: illustrative IMU 100 Hz and GPS 1 Hz; no sustained-device rate or tail claim. |
| [Physical S1 protocol](../../android/acquisition/imported/S1_Android_Acquisition_Spike/docs/S1_Device_Test_Protocol.md) | Version 1.0, predeclared criteria retained unchanged | Governs actual S1-PASS/CONDITIONAL/FAIL/PENDING classification. |
| [Import inventory](../architecture/imports/WP-02.1_S1_ANDROID_ACQUISITION_IMPORT.json) and [I-18 legacy mapping](../../contracts/I18_LEGACY_S1_MAPPING.md) | Existing checked-in artifacts, unchanged | Import integrity and strict session migration rules; neither invents missing physical or session metadata. |

## Decision by protocol criterion

| Criterion | Available evidence | Adjudication |
| --- | --- | --- |
| Available low/mid/high-tier phones and declared supported-device matrix | Synthetic device label only | PENDING; no device/API generalization. |
| Calibrated accelerometer and gyro availability, steady A/C median rates/p99 source intervals | One synthetic 10 ms interval per sensor | PENDING; a one-interval example cannot establish sustained rate or p99 behavior on a phone. |
| No unexplained steady source gap >=1 s and cause analysis for duplicates/non-monotonic/reordered callbacks | Per-stream synthetic sample ordering only | PENDING; no physical steady phases or cause analysis. |
| At least 30 continuous screen-off minutes with live foreground service | No lifecycle/screen evidence | PENDING. |
| GPS provider/provenance and separate GNSS-status diagnostics | Two synthetic GPS examples; no physical status stream | PENDING physical provenance coverage; no ten-hertz GNSS requirement introduced. |
| Chunk/hash/session durability, deliberate interruption, low-storage/recovery/export behavior | No complete physical I-18 session/chunk evidence | PENDING. |
| Battery drain and workload completion without thermal shutdown | No battery/thermal workload evidence | PENDING; no numerical acceptance threshold fabricated. |
| Navigation accuracy or integrated ten-event demo | Outside S1 and absent from this fixture | NOT ADJUDICATED by S1; no performance claim. |

No observed failure in a tiny synthetic example is not a physical pass. Missing evidence also does not prove S1-FAIL. S1-CONDITIONAL requires demonstrated physical feasibility and bounded limitations; synthetic-only success cannot justify it. The protocol's pending classification is therefore the evidence-supported result.

## Replay and demonstration boundary

This fixture has no normal-session I-18 COMPLETE manifest, authenticated boot/configuration identities, or verified chunk sequence. The six records are grouped by stream rather than globally chronological: the gyroscope example starts at 1,002,000,000 ns after the accelerometer example at 1,010,000,000 ns in file order. The strict replay scheduler must reject that regression instead of sorting or repairing source evidence. The fixture remains valid for its per-stream contract test and explicitly diagnostic synthetic analysis. The assignee-designated [storyboard](../architecture/SIH26168_WP15_7_Demo_Narrative_Storyboard_v1.md) freezes narrative/evidence expectations, not missing I-07/I-08/I-11/I-15 scientific results.

## Reproduction, review and next evidence

Use the existing round-trip command and 21 focused tests listed above, plus `python ci/verify_repository.py all`; PR evidence records exact-head policy results. No code, threshold, input bytes, imported protocol, generated graph or private dataset changes in this adjudication.

R5/R6 must supply the protocol's actual phone/session matrix, immutable input manifests/chunk hashes, steady and screen-off intervals, permission/service/provider events, power/thermal evidence and recovery/fault results. Assess the predeclared criteria without changing thresholds after seeing outcomes. Preserve incompleteness and limitations. The designated architecture/CODEOWNER reviewers issue the current-evidence decision and authorized closure; parent #6 and child #54 remain open until that process is satisfied. New physical evidence requires a superseding versioned adjudication linked to its exact inputs; do not rewrite this synthetic record into a physical result.

Prepared with Codex assistance from the user-selected fixture and existing protocol. No physical session, runtime renderer, rehearsal or scientific validation was fabricated.
