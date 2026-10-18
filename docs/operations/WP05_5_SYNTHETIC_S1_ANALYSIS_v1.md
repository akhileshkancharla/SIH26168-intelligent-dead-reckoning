# WP-05.5 synthetic S1 evidence analysis v1

Relates to #6 and #53. Analysis date: 2026-10-18 IST. Classification: `SYNTHETIC_PUBLIC_TEST_ONLY`. Physical-device gate: `S1-PENDING-DEVICE-EVIDENCE`.

## Inputs and method

The assignee selected the [canonical fixture](../../contracts/fixtures/s1_acquisition_round_trip_v1_fixture.json) as the frozen analysis input. Exact file-byte SHA-256: `44068a9b5beeade2581a7914707596e5b88b6d85cdcec5f9016752908728f2bb`. The [round-trip verifier](../../tools/acquisition/s1_fixture_roundtrip.py) reports canonical-JSON SHA-256 `869838c689b93b9af69dd29b51b83db803d3acb15bb05f857e1542ff96d57446`; these identify different serializations and must not be interchanged. The fixture contains six records: four I-01 sensor observations and two I-02 location observations, one synthetic session, three streams, `CLOCK_BOOTTIME`, and explicitly synthetic provenance.

The [imported predeclared physical protocol](../../android/acquisition/imported/S1_Android_Acquisition_Spike/docs/S1_Device_Test_Protocol.md), [immutable import inventory](../architecture/imports/WP-02.1_S1_ANDROID_ACQUISITION_IMPORT.json), and [legacy manifest mapping](../../contracts/I18_LEGACY_S1_MAPPING.md) remain unchanged. The fixture is a contract example, not an I-18 COMPLETE physical-session manifest or full ten-event navigation run. Do not synthesize missing boot/config/device/chunk metadata or upgrade it to normal-session replay eligibility.

Validate the fixture before calculating. Preserve record order and group by `(session_id, clock_id, stream_id)`; never compare independent clocks/boots or sort away malformed input. For each group, compute adjacent source-time differences, original sequence differences, and `arrival_elapsed_realtime_ns - source_timestamp_ns`. With two samples, illustrative rate is `1e9 / delta_ns`. There is only one interval per stream, so this is neither an estimator-output measurement nor a defensible sustained-rate distribution.

## Observed synthetic values

| Stream | Records | Source interval | Illustrative fixture rate | Arrival minus source | Duplicate/backward source times / missing sequence increments |
| --- | ---: | ---: | ---: | --- | --- |
| sensor-accelerometer | 2 | 10,000,000 ns | 100 Hz | 50,000 ns; 60,000 ns | 0 / 0 / 0 |
| sensor-gyroscope | 2 | 10,000,000 ns | 100 Hz | 70,000 ns; 80,000 ns | 0 / 0 / 0 |
| location-gps-provider | 2 | 1,000,000,000 ns | 1 Hz | 100,000 ns; 120,000 ns | 0 / 0 / 0 |

These are fixture arithmetic, not delivered Android rates or measured hardware latency. The sensor examples span only 10 ms each, and the GPS examples span one second. No IMU source gap of one second or more occurs in this tiny example; it does not establish gap-free sustained delivery. The GPS one-second interval is not an IMU failure and no 10 Hz GNSS threshold is imposed. Records are grouped examples, not evidence of global callback arrival ordering; cross-stream physical reordering cannot be adjudicated from them.

## Coverage and missing evidence

| Requested analysis | Available result | Physical interpretation |
| --- | --- | --- |
| Rates / positive intervals | One positive interval per stream, values above | Insufficient for steady Test A/C sustained rate and tail behavior on any phone tier. |
| Gaps / ordering / provenance | Fixture schema, finite-value, field-mask, evidence identity, per-stream order and round-trip checks pass | Synthetic software coverage only; no physical callback batching/reordering or recurring-gap cause analysis. |
| Screen-off | No screen/power/service lifecycle stream or 30-minute interval | NOT OBSERVED; Test B remains pending. |
| Battery | No charge, state, power-mode, health or duration evidence | NOT OBSERVED; no drain estimate or invented consumption threshold. |
| Thermal | No thermal-status events or workload completion | NOT OBSERVED; no shutdown/safety conclusion. |
| Finalization / recovery / export | Import inventory integrity verified by existing tests | No physical session/chunk durability, interruption or low-storage result follows from the canonical fixture. |
| Device/API coverage | Synthetic device identity only | No phone tier, OEM/API support claim or three-phone generalization. |

## Reproduction and verification

Use Python 3.13 with `jsonschema==4.23.0` and `referencing==0.35.1` in an external environment (the project requires Python >=3.11). Run:

```text
python tools/acquisition/s1_fixture_roundtrip.py
python -m unittest ci.tests.test_s1_reduced_import_inventory tools.bootstrap.tests.test_s1_fixture_round_trip
python ci/verify_repository.py all
```

Observed round-trip output: `PASS: S1 fixture round-trip records=6 i01=4 i02=2 sha256=869838c689b93b9af69dd29b51b83db803d3acb15bb05f857e1542ff96d57446`. All 21 focused inventory/round-trip tests passed. For the table, extract each record's provenance session/stream and timestamp clock, retain order within each group, and apply the formulas above. The exact fixture bytes are frozen by the file hash; the calculation uses integer nanoseconds before conversion to hertz. Full repository-policy outcomes are recorded at the report PR head.

## Conclusion and handoff

The supplied input supports reproducible synthetic contract/timing analysis only. It supplies none of the required screen-off, battery, thermal or phone-matrix evidence. The predeclared physical verdict remains `S1-PENDING-DEVICE-EVIDENCE`; Issue #53 and parent #6 stay open for the missing physical coverage. WP-05.6 must carry this evidence limit forward and cannot convert an illustrative fixture rate into S1-PASS, S1-CONDITIONAL, navigation accuracy or integrated-demo evidence. R5/R6 collect the missing protocol evidence; the designated reviewers adjudicate it through the authorized workflow. Analysis prepared with Codex assistance using the existing fixture and protocol; no private recording or generated raw data is committed.
