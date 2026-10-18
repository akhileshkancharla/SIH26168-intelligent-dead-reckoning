# WP-02.2 SensorManager contract adapter

Relates to #3 and #32. This implements the C-01 I-01 source adaptation boundary using the existing raw sensor schema and common evidence envelope. The hash-verified S1 import remains unchanged.

## Behavior

`ContractSensorEventListener` captures callback arrival using elapsed realtime and copies the callback array before returning. `SensorContractAdapter` preserves the Android body axes, units, source timestamp, accuracy, sensor ID/type/name/vendor/version, and observation values. Each session has independent per-sensor sequences and globally unique evidence IDs. No bias removal, interpolation, resampling, coordinate rotation, gap filling, or C-07 update occurs here.

The raw recorder receives every snapshot first. Only observations that satisfy existing I-01 shape, finite-value, accuracy, metadata, and time checks reach `LIVE_DEVICE` shared ingress. Duplicate or backward source times remain in evidence, keep their original timestamps, receive a typed invalid gate, and never reach runtime. Sequence gaps at ingress therefore remain observable. A recorder exception propagates and prevents runtime delivery; the session owner must stop recording and report degraded/incomplete evidence. A new adapter is required after session/boot changes. Reentrant publication fails explicitly.

Supported I-01 sensor types are exactly the existing schema values: accelerometer (1), magnetic field (2), gyroscope (4), and ambient temperature (13). Uncalibrated/other Android types are retained as invalid diagnostic observations, without truncating arrays or inventing a supported type. Malformed observations are diagnostic evidence, not schema-valid I-01 claims, and require the recorder's diagnostic path rather than serialization as accepted contract records. No scientific threshold is introduced.

## Integration and verification

The session owner supplies a durable `SensorEvidenceRecorder` and `SourceBoundNavigationIngress(LIVE_DEVICE, sink)`, registers the listener with its user-started SensorManager/service lifecycle, and handles permission, availability, accuracy events, registration failures, and recording failure. Construct the adapter only after session context is available. This deliverable provides the adapter and listener; it does not connect the replay launcher to live sensors or replace the imported S1 service/writer.

Run `gradle -p android testDebugUnitTest lintDebug`, `python ci/generate_contract_bindings.py --check`, and `python ci/verify_repository.py all`. Regressions cover preserved evidence identity/time/values, immutable snapshots, independent sensor streams, duplicate/backward time rejection, malformed callbacks, optional temperature, and recorder failure before runtime publication. Build/test outcomes are recorded in the PR at its exact head. Tests are synthetic and do not establish physical rates, screen-off delivery, battery, thermal behavior, S1 completion, or navigation accuracy.

## Attribution

Callback semantics follow the imported S1 logger's `RecordingService.onSensorChanged` and Architecture Revision 3 I-01. The imported artifact and inventory remain unchanged. Adaptation and regressions prepared with Codex assistance.
