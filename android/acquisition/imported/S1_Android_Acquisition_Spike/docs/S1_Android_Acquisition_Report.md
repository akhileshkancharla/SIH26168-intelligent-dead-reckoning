# S1 Android Sensor Acquisition and Timing Feasibility Report

Report version: 1.0  
Evidence cutoff: 2026-09-01  
Executive gate verdict: **`S1-PENDING-DEVICE-EVIDENCE`**

> No physical Android device recording was supplied or collected in this
> environment. The completed implementation, build/static checks and synthetic
> fixtures cannot establish screen-off, device-rate, GNSS, battery or thermal
> feasibility on real phones.

## 1. Executive gate verdict

The bounded logger and offline analysis package implement the S1 evidence path.
The scientific clock/provenance contract is explicit, raw Android axes are
retained, requested and delivered rates are separate, GNSS status is not treated
as a position, and no network/Play-services dependency exists. The physical
device matrix remains empty. Therefore the only defensible verdict is
`S1-PENDING-DEVICE-EVIDENCE`; S1 has not passed.

## 2. Scope and exclusions

Included: native Kotlin acquisition through official `SensorManager` and
`LocationManager`, a user-started location foreground service, local crash-aware
JSONL chunks, session export, metadata/context logging, a read-only analyzer,
deterministic fixtures, tests, and an exact device protocol.

Excluded: estimator design or S2 modification, bias correction, canonical axis
conversion in the logger, ML, map matching, navigation UI, routing, cloud,
network upload, Google Play services, fused-location scientific input, external
navigation apps, OBD-II/vehicle data, raw pseudorange positioning, IO-VNBD and
production architecture freezing.

## 3. Official Android source verification

Platform-sensitive decisions were checked on 2026-09-01 against official
Android documentation:

| Decision | Verified basis | Implementation |
| --- | --- | --- |
| Current stable SDK/tooling | [AGP 8.13.2 release notes](https://developer.android.com/build/releases/gradle-plugin) specify Gradle 8.13, JDK 17, API 36 support and default Build Tools 35.0.0; [Android 16 setup](https://developer.android.com/about/versions/16/setup-sdk) specifies compile/target 36 | AGP 8.13.2; Gradle 8.13; JDK 17; compile/target 36; Build Tools 35.0.0. API 37 was not selected because the official Android 17 setup page labels its platform as a preview and the platform package was unavailable from the SDK repository used for reproduction. |
| Kotlin | AGP 8.13.2 release notes state Kotlin 2.3 support; the official [Kotlin releases](https://kotlinlang.org/docs/releases.html) list 2.3.10 as a bug-fix release | Explicit Kotlin Android plugin/compiler 2.3.10 |
| Sensor clock | [`SensorEvent.timestamp`](https://developer.android.com/reference/android/hardware/SensorEvent#timestamp) is nanoseconds and uses the `elapsedRealtimeNanos` time base per sensor | Original `event.timestamp` plus callback-arrival elapsed realtime |
| Screen-off acquisition host | [Sensors overview](https://developer.android.com/develop/sensors-and-location/sensors/sensors_overview) states continuous sensors do not deliver to background apps from API 28 and recommends foreground/foreground-service collection | Dedicated foreground service; min SDK 28; no activity-owned listener |
| High sensor rates | Same official sensor guidance requires `HIGH_SAMPLING_RATE_SENSORS` for high motion-sensor rates and notes privacy-toggle rate limiting | Permission declared; actual rate measured |
| Location time | [`Location.getElapsedRealtimeNanos`](https://developer.android.com/reference/android/location/Location#getElapsedRealtimeNanos()) is monotonic, survives deep sleep and can be compared with callback elapsed realtime within one boot | Source and arrival both preserved; age calculated |
| Provider provenance | Named-provider [`requestLocationUpdates`](https://developer.android.com/reference/android/location/LocationManager#requestLocationUpdates(java.lang.String,long,float,android.location.LocationListener,android.os.Looper)) | Explicit `GPS_PROVIDER`; no criteria/fused provider |
| Mock indication | [`Location.isMock`](https://developer.android.com/reference/android/location/Location#isMock()) identifies framework mock locations; pre-31 fallback is documented deprecated API | API-gated `isMock` / `isFromMockProvider` |
| GNSS status | [`GnssStatus.Callback`](https://developer.android.com/reference/android/location/GnssStatus.Callback) reports receiver/satellite status; registration requires fine location | Separate diagnostic stream, never position evidence |
| FGS permission/start | Official [location FGS type](https://developer.android.com/develop/background-work/services/fgs/service-types#location) and [launch guide](https://developer.android.com/develop/background-work/services/fgs/launch) require location permissions/type and constrain background starts | Visible-button start; `location` type; both FGS permissions; no boot/background start |
| Thermal state | Official [`PowerManager`](https://developer.android.com/reference/android/os/PowerManager#getCurrentThermalStatus()) exposes status/listener from API 29 | API-gated status and change events |

No archived sample repository or third-party article is used as authority for
current Android behavior.

## 4. Implemented acquisition architecture

The visible `MainActivity` owns Start, Stop and explicit export. Start verifies
fine location and then calls `startForegroundService`. `RecordingService`
promotes itself with the declared location type, creates a dedicated
`HandlerThread`, registers all available selected sensor instances, requests the
named GPS provider, registers GNSS status, and records lifecycle/screen/battery/
thermal context. Sensor callbacks do minimal copying/serialization on the
dedicated thread. No estimator owns or modifies evidence.

`SessionWriter` appends JSONL to a bounded partial chunk, flushes and `fsync`s
periodically, rotates at 5 MiB, atomically finalizes each chunk, and hashes it.
The final manifest is also atomically written. App-private sessions are exported
only via the document picker.

## 5. Timestamp and clock semantics

Sensor and location source times are preserved exactly. Both official sources
are mapped to `android.elapsed_realtime_ns`; callback arrival is sampled from
`SystemClock.elapsedRealtimeNanos()` in the same boot. Source-to-arrival age is
therefore measurable. The logger does not replace source time, fabricate missing
time, interpolate, reorder, regularize batches, or use wall clock for scientific
intervals. Wall time is auxiliary only and clocks cannot be compared across
devices or boot cycles.

## 6. Sensor and location provenance

Each sensor instance has its own identity/sequence and complete Android metadata.
Values remain in original Android axes and documented SI units; uncalibrated
variants retain any appended bias/drift estimates as raw callback values.

Location fixes state `provider: gps`, field availability, source/arrival time,
age and mock indication. `GnssStatus` is a separate receiver-status/satellite
stream. Raw GNSS measurements are omitted. FusedLocationProviderClient is absent.
Different GNSS-family streams are not represented as independent fixes.

## 7. Foreground-service and permission model

The activity starts recording only from a visible button after fine-location
grant. Manifest permissions are fine/coarse location, foreground service,
foreground-service location, high-rate sensors and notification display. The app
does not request background location because the start is visible and ongoing
work is a location foreground service. API 33+ notification state is logged.
Collection uses `START_NOT_STICKY`; process death cannot silently start a new
recording. A persistent notification provides Stop.

## 8. Logging durability and recovery

Every session begins with `INCOMPLETE`. Chunks use `.partial`, periodic durable
flush, atomic rename and SHA-256. The manifest lists ordered path/size/hash.
At next process creation, an abandoned partial is finalized and a recovery
manifest explicitly marks `complete:false`; missing callback data is never
invented. Free-space reserve is 100 MiB and the session cap is 2 GiB. Export is
one complete session ZIP.

Force-stop is not claimed to auto-recover. The only bounded claim is preservation
and classification of already written bytes upon a later manual relaunch.

## 9. Automated test results

The frozen verification record is `results/verification_summary.json`; raw logs
and JUnit/lint reports are in `results/`.

| Verification set | Passed | Failed | Skipped/pending | Result |
| --- | ---: | ---: | ---: | --- |
| Host analyzer tests | 12 | 0 | 0 | pass |
| Android JVM tests, debug variant | 5 | 0 | 0 | pass |
| Android JVM tests, release variant | 5 | 0 | 0 | pass |
| Android instrumentation tests | 0 | 0 | 6 | compiled into a test APK; no device was available to execute them |
| Physical protocol groups, A-D across three tiers | 0 | 0 | 12 | pending device evidence |

`test`, `lint`, `assembleDebug`, and `assembleDebugAndroidTest` completed in one
Gradle invocation: 109 actionable tasks, 16 executed and 93 up-to-date. Android
lint found 0 issues. The debug APK SHA-256 is
`00a7ef273028f266144efa30fd779b7d8e14bd41a609fa7e54dbcd80ad791930`;
the instrumentation APK SHA-256 is
`ad7a32371d2b71ab22c5ba8a9365aabdb880307e5eeccc2d345a7fce2d207f30`.
The deterministic fixture analyzer processed 13 records with 0 errors. No
instrumentation or physical-device test is counted as passed.

## 10. Physical-device matrix

| Tier | Device | Android/API | A | B | C | D | Evidence status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Older/low | Not supplied | — | not run | not run | not run | not run | pending |
| Mid-tier | Not supplied | — | not run | not run | not run | not run | pending |
| Current/high | Not supplied | — | not run | not run | not run | not run | pending |

Physical-device tests passed: **0**. Physical-device tests skipped/pending: **12
test groups** (A–D across three target tiers; D contains separately adjudicated
subtests). This is not a device pass.

## 11. Delivered-rate distributions

No physical distributions exist. The analyzer reports count, duration, requested
and delivered rate, mean/median/stddev/min/max/p90/p95/p99/p99.9 interval, and
effective-rate distribution per stream. Synthetic fixture output only verifies
the calculation path and must not appear in a device claim.

## 12. Gap, batching and reorder findings

No physical findings exist. The deterministic fixture deliberately retains and
detects one duplicate, one non-monotonic timestamp and one large gap. Callback
order remains file order. A transparent 2 ms arrival-separation heuristic reports
delivery bursts without claiming direct hardware-FIFO batch identifiers.

## 13. Screen-off findings

No physical screen-off test was run. The logger records interactive-state
transitions and runs acquisition from a foreground service, but documentation
and compilation cannot prove 30-minute screen-off survival on any OEM phone.

## 14. Battery and thermal findings

No physical findings exist. Battery broadcast state and API 29+ thermal status
are logged. The analyzer reports battery change only when at least two readings
exist and labels it coarse evidence, not component attribution. No universal
power threshold is claimed.

## 15. GNSS/location findings

No physical fixes were supplied. The analyzer will report fix count/rate/age,
provider distribution and missing accuracy/speed/bearing availability. An indoor
no-fix test is not automatically a logger failure; provider state, sky view and
IMU continuity must be interpreted together.

## 16. Device/API limitations

- Sensor presence, rate, FIFO, power, batching and OEM screen-off policy vary.
- API 28 has no public thermal-status API; absence is explicit.
- The requested 100 Hz sensor period and 10 Hz location interval are requests,
  not delivery guarantees.
- Device microphone privacy controls may limit motion-sensor rate even with the
  high-sampling permission.
- GPS provider behavior and GNSS status depend on hardware, settings, sky view,
  permissions and power policy.
- Battery percentage is coarse. A later controlled S8 workload study is needed.
- App/process/user/OEM termination can lose events not yet delivered or written.
- Min SDK 28 is a deliberate spike boundary, not the final supported matrix.

## 17. Privacy and safety assessment

The application is offline and omits unique device identifiers, but raw location
and motion are sensitive. Export is user-controlled; public repository inclusion
is prohibited by protocol. Driver interaction is prohibited during motion. Safe
passenger, mount, bench and controlled low-storage procedures are specified in
`S1_Privacy_and_Safety.md` and the protocol.

## 18. S1 decision

Predeclared decision rules appear in the device protocol and were frozen before
physical results. Current decision: **`S1-PENDING-DEVICE-EVIDENCE`**. This report
must not be relabeled `S1-PASS` until actual named-device sessions satisfy those
rules. One successful phone cannot establish universal Android feasibility.

## 19. Implications for S3 alignment

S3 should consume exported raw evidence through an adapter, retain the session/
stream/sequence/source-clock identity, and perform any Android-device-axis to
canonical body/NED conversion outside the logger. S3 must characterize mount
orientation and time alignment from physical recordings; it must not infer
alignment feasibility from the synthetic fixture.

## 20. Implications for Architecture Revision 3

The spike supports a provisional separation between acquisition, canonicalization
and navigation truth. Architecture Revision 3 may reference this recording
contract and named-provider provenance, but must not freeze a universal rate,
device matrix, screen-off guarantee, battery budget, or production persistence
design until physical S1 and integrated S8 evidence exists.

## 21. Unresolved decisions

1. Which three named phones and OS versions define the claimed support matrix?
2. What estimator input-rate/window requirements emerge from S3/S4?
3. Are the 20 Hz/p99 100 ms spike minima sufficient after real replay?
4. Does any target OEM require a documented power-policy mitigation?
5. Is raw GNSS diagnostic value worth a separately gated v2 stream?
6. What quantitative power/thermal/storage budget will S8 freeze?
7. How will mount orientation and cross-device calibration be established?
8. What retention/access policy will govern raw route recordings?

## 22. Exact reproduction instructions

```bash
unzip S1_Android_Acquisition_Spike_v1.zip
cd S1_Android_Acquisition_Spike
java -version                     # must be JDK 17
./gradlew --version               # Gradle 8.13
./scripts/run_host_tests.sh
./gradlew --no-daemon test
./gradlew --no-daemon lint
./gradlew --no-daemon assembleDebug
./gradlew --no-daemon assembleDebugAndroidTest
PYTHONPATH=. python3 -m analyzer.s1_analyzer \
  fixtures/deterministic_session --output results/reproduced_fixture_analysis
sha256sum app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Then execute `S1_Device_Test_Protocol.md` without changing the predeclared rules.
For every exported session:

```bash
./scripts/analyze_session.sh exported_session.zip results/<run-id>
```

Return the raw exported session ZIPs, analyzer outputs, completed device matrix
and run sheets, APK SHA-256/build identity, phone-tier rationale, and incident
notes for final S1 adjudication.
