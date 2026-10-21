# WP-15.6 synthetic rehearsal preflight and incident review v1

Relates to #16 and #111. Attempt date: 2026-10-18 IST. **Result: `STOPPED_PREFLIGHT`; Events 1–10 `NOT_EXECUTED`.** This is an executed synthetic eligibility check and desk-review incident record, not a completed integrated or physical-device rehearsal.

## Frozen inputs and executed method

The assignee selected the [canonical six-record S1 fixture](../../contracts/fixtures/s1_acquisition_round_trip_v1_fixture.json) and [approved storyboard](../architecture/SIH26168_WP15_7_Demo_Narrative_Storyboard_v1.md). The [frozen evidence plan](https://github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning/blob/c38d33b6e92391057cb1989149a2c15d319e21e7/demo/scenarios/ten_event_synthetic_evidence_plan_v1.json) is identified by commit `c38d33b6e92391057cb1989149a2c15d319e21e7` and plan SHA-256 `4171cad6d3ed983aa8028ba3c56e22867926f6c7971c42f62aea7ce65a4f294b`. All three source-file hashes matched its input freeze in this repeated check. This is the corrected PR #196 review candidate, not a claim of owner approval; designated acceptance remains pending. Event 3 now maps output continuity to I-07/I-08/I-16; I-15 is confined to recovery Events 8–10. The repeated mapping consistency guard passed.

Executed Python preflight: load that immutable plan; check each input hash against repository bytes; read fixture records in their original order; compare adjacent source epochs without sorting; list absent I-18 session keys; enumerate supplied payload types; stop when normal-session eligibility is false. Existing contract round-trip and all 21 inventory/round-trip tests also passed. A contract-valid fixture is not automatically an eligible integrated replay.

Observed source epochs in original record order (ns): `1000000000, 1010000000, 1002000000, 1012000000, 1020000000, 2020000000`. At zero-based index 2 the source epoch falls from `1010000000` to `1002000000`. The strict [existing replay scheduler](../../android/app/src/main/java/org/sih26168/app/replay/DeterministicReplayScheduler.kt) rejects regressive schedules and must not silently sort this evidence to force a run. Its original fixture remains unchanged.

Absent I-18 root keys observed: `app_build`, `boot_id`, `chunks`, `clock_id`, `config_hash`, `device_profile`, `loss_counts`, `privacy_class`, `status`, and `streams`. Available payload types are only `LocationGnssFix` and `RawSensorSample`. There are no supplied I-07/I-08 scientific outputs, I-11 matcher proposals, or I-15 rejection/dwell/acceptance results. The [legacy mapping](../../contracts/I18_LEGACY_S1_MAPPING.md) prohibits inventing session metadata or upgrading diagnostic evidence to COMPLETE replay.

## Ten-event desk-review ledger

| Event | Required behavior | Observed execution / evidence gap |
| --- | --- | --- |
| 1 | GNSS-aided anchor | NOT_EXECUTED; no eligible session or integrated I-07/I-08 start. |
| 2 | Declared software outage | NOT_EXECUTED; no executed I-14 mask interval. |
| 3 | Scientific output continuity | NOT_EXECUTED; no measured output-rate distribution or gaps. |
| 4 | Inertial propagation | NOT_EXECUTED; no integrated core state/covariance run. |
| 5 | Turn during outage | NOT_EXECUTED; the input fixture supplies no turn demonstration. |
| 6 | Uncertainty growth | NOT_EXECUTED; no computed I-08 sequence. |
| 7 | Bounded map candidates | NOT_EXECUTED; no runtime I-11 matcher evidence. |
| 8 | Biased return rejected | NOT_EXECUTED; no integrated gate/NIS/rejection result. |
| 9 | Credible return accepted | NOT_EXECUTED; no configured dwell/consistency/accepted update. |
| 10 | Smooth display recovery and comparison | NOT_EXECUTED; no eligible scientific/reference run and comparison report. |

The storyboard supplies expected behavior and disclosure wording for all events, not observed outcomes. Related PR #170 at `b8cd6e56e7f1a116316c4c58f72ce5b3273677cc` passed 73 JVM tests, lint and instrumentation compilation in a separate source build; those synthetic presentation tests remain separate evidence and do not turn this stopped preflight into a rendered rehearsal.

## Incident review and corrective actions

| Incident | Evidence / consequence | Responsible action and exit criterion |
| --- | --- | --- |
| R-01 ineligible session input | Fixture root lacks required I-18 metadata/chunks; normal replay false. | R5/R6 provide a separately versioned COMPLETE session with authentic metadata, verified relative chunks/hashes and explicit synthetic/recorded classification. Preserve this fixture as the contract example. |
| R-02 regressive global source order | Index 2 regression; strict scheduler must reject it. | R5/C-12 owner supply eligible ordered source evidence through the approved reader/adapter contract. No silent sorting or timestamp repair. Revalidate before playback. |
| R-03 missing scientific event evidence | No state/covariance, matcher or rejection/acceptance outputs. | Navigation/map/demo owners integrate actual producers and bind event assertions to exact evidence IDs/configuration. Missing matcher stays UNAVAILABLE. |
| R-04 device/capture proof absent | No Android device connected for this attempt; no executed renderer/radio trace or recording. | R5/R6 run the accepted build/scenario and capture approved footage plus evidence. Keep replay/demo/outage disclosures and map attribution visible. |

Stop before Event 1 until the relevant input/runtime gates are satisfied. Re-run this preflight on newly identified immutable inputs, then execute the complete ten-event scenario and record timecodes, failures, corrective actions and designated review. No incident is marked resolved by the existence of a checklist. Issues #111/#16 remain open; the physical S1 and Issue #77 airplane-mode gates are unaffected.

## Reproduction and limits

Use Python >=3.11 with the declared jsonschema/referencing dependencies for existing fixture tests and `python ci/verify_repository.py all`. For the preflight, preserve the epoch list above and compare each adjacent pair; check the listed I-18 keys directly in the fixture root; compare the supplied payload-type set to the required event interfaces. Exact-head policy outcomes are recorded in the PR. This one-file report changes no runtime code, original input, protocol, thresholds, generated graph or private data. Prepared with Codex assistance from the user-selected inputs and actual preflight observations.
