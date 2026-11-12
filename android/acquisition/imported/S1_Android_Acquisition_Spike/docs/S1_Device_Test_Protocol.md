# S1 Physical-Device Test Protocol

Protocol version: 1.0 — predeclared before examining physical-device evidence.

## 1. Purpose and gate discipline

This protocol tests Android acquisition timing, provenance, delivery continuity,
durability and resource behavior. It does not test navigation accuracy or the S2
estimator. Synthetic/emulator results validate software only. If fewer than
three physical phones are available, execute every applicable test but retain a
limited/pending gate and do not generalize.

Target tiers, selected from phones genuinely available to the team:

1. older/low-tier phone;
2. mid-tier phone;
3. current/high-tier phone.

Record manufacturer/model, Android/API, RAM/storage class, release year, sensor
inventory, battery health caveat, power mode and rationale for the tier. Do not
record serial, IMEI, Android ID, telephone number or account identifiers.

## 2. Predeclared feasibility rules

The intended smartphone navigation output is approximately 10 Hz, while the
exact estimator input-rate contract remains unresolved. These thresholds are
therefore bounded S1 engineering criteria, not universal Android requirements:

- On each claimed-supported phone, calibrated accelerometer and gyroscope must
  both be present. During steady Test A and C intervals, each must deliver a
  median rate of at least 20 Hz and p99 positive source interval no greater than
  100 ms. This provides at least two median-rate IMU samples per nominal 10 Hz
  output and makes sustained sub-10 Hz delivery visible.
- No unexplained source gap of 1 s or more is permitted in a steady phase.
  Declared start/stop, provider disablement, process recreation, thermal event,
  or deliberate fault intervals remain evidence and are classified, not hidden.
- Duplicate, non-monotonic and callback-reordered events must be counted. Any
  occurrence requires cause analysis; unexplained recurrence that invalidates
  chronological ingestion prevents `S1-PASS`.
- Test B must contain at least 30 continuous screen-off minutes while the
  user-started location foreground service remains alive. The log must be
  complete or explicitly recovered, and IMU delivery must remain analyzable.
- The named location provider must remain `gps`; GNSS status must remain a
  separate diagnostic stream. Fix rate is measured but no 10 Hz GNSS-fix
  threshold is imposed because the 10 Hz requirement concerns planned output,
  not proven Android GNSS supply.
- Storage/hash/session verification must show zero unexplained missing or
  corrupted finalized chunks. A deliberately interrupted session must be
  recovered as `complete: false`, never silently relabeled complete.
- Battery and thermal evidence must be reported. No universal consumption
  threshold is invented; `S1-PASS` requires that the tested workload completes
  safely without thermal shutdown, uncontrolled storage growth or operationally
  unacceptable drain on the declared device. Quantitative acceptance can be
  frozen later from S8 integration requirements.

Classification:

- `S1-PASS`: all criteria hold on every claimed-supported tested phone, with
  complete, hash-valid evidence and device limitations documented.
- `S1-CONDITIONAL`: core feasibility is demonstrated but a bounded device/API,
  permission, OEM, rate, power or recovery limitation needs a scoped mitigation
  and the support claim is narrowed accordingly.
- `S1-FAIL`: the acquisition path cannot provide coherent/adequate evidence on
  the intended target class, or provenance/durability defects prevent scientific
  use and no bounded remedy is established.
- `S1-PENDING-DEVICE-EVIDENCE`: physical evidence is absent or too limited for
  adjudication. Software-only success cannot elevate this verdict.

One phone never establishes universal Android support.

## 3. Common preparation

For every phone and every test:

1. Build from the delivered archive with JDK 17 and the pinned SDK/toolchain.
   Save `sha256sum app-debug.apk` and the Git commit if the source is in Git.
2. Install the same APK. Record app version, APK hash, phone tier, Android/API,
   free storage, initial battery percentage/charging, thermal state, battery
   saver, microphone privacy-toggle state, location enabled state and granted
   permissions.
3. Disable unrelated test-disrupting applications where reasonable, but do not
   change OEM power policies silently. Record every non-default exemption.
4. Place/mount the phone consistently and document orientation in words/photo
   outside the raw session. The logger itself retains Android device axes.
5. Use one recording session per named test. Note UTC start/stop only as
   auxiliary run-sheet metadata.
6. Stop explicitly, export the complete session, run the analyzer, and keep the
   unmodified export plus results. If the app/process fails, do not retry over
   the evidence; preserve the incomplete recovery artifact and start a new run.

Suggested run ID: `S1-<device_alias>-<test>-<attempt>-YYYYMMDD`. Keep the alias
mapping privately; do not replace the logger's session UUID.

## 4. Test A — stationary, screen on

- Minimum 5 minutes.
- Phone motionless on a stable surface; screen interactive throughout.
- Record all available selected sensor types, GPS-provider location, GNSS
  status, lifecycle, thermal and battery evidence.
- Note indoor/outdoor/sky-view conditions. GNSS absence indoors is not an IMU
  failure, but provenance and provider state must still be explicit.
- Export and analyze. Confirm requested versus delivered rates are distinct.

## 5. Test B — stationary, screen off

- Minimum 30 minutes after recording begins.
- Start from the visible activity. Wait 30 seconds, turn the screen off once,
  then do not interact for at least 30 minutes.
- Do not grant an undocumented battery-optimization exemption and do not hold a
  test-only wake lock. If an exemption is necessary, rerun as a separately
  labeled conditional experiment.
- Turn the screen on, wait 30 seconds, stop explicitly, export and analyze.
- Verify screen transition records, callback delivery/latency before/during/after
  screen off, service continuity, chunk hashes and thermal/battery observations.

## 6. Test C — motion session

- 30–60 minutes where safely and lawfully practical.
- Prefer passenger-operated recording with the phone secured in a mount. A
  walking or bench-motion substitute is allowed but must be labeled accurately
  and cannot establish vehicle-motion feasibility.
- The driver must never interact with the phone. Start/stop only while parked or
  by a passenger.
- Include open-sky and, if safely available, a benign obstructed-sky segment;
  do not intentionally enter unsafe areas or violate traffic rules.
- Record route/environment notes outside the logger. Do not publish raw route.
- Analyze GNSS fix age/provider, IMU rates/gaps/bursts, lifecycle, screen state,
  thermal state, battery change and hash completeness.

## 7. Test D — lifecycle and fault stress

Use short, separate sessions/subtests and record the exact action time. Do not
combine outcomes or count expected failures as normal continuity.

| Subtest | Procedure | Required evidence |
| --- | --- | --- |
| Activity background | Start visibly, press Home, wait 5 min, return, stop | lifecycle events; service/IMU continuity |
| Screen off/on | Start, screen off 5 min, on, stop | screen state and continuity |
| UI recreation | Start, rotate/change configured UI state or use developer activity recreation without killing service | `activity_recreated`; service continuity |
| Service stop/restart | Stop explicitly, confirm final manifest, start new session | two distinct IDs/manifests |
| Permission denial | Revoke/deny fine location before Start | clear UI error; no recording starts |
| Permission loss | While safe, revoke location during an active short test | explicit error/stop or provider evidence; no fabricated fixes |
| Location disabled | Disable location during a safe short run, restore it | provider-state events and fix gap |
| Sensor unavailable | Use a device/emulator lacking an optional sensor | explicit `available:false`; required accel/gyro limitation |
| Low storage | Use a disposable test profile/emulator or controlled quota; never fill a personal phone | explicit storage stop and recoverable/finalized evidence |
| Incomplete recovery | Terminate the process in a controlled development test, relaunch, then export recovered session | `complete:false`, recovery stop reason, valid existing chunks |

Do not use Android force-stop as proof of automatic recoverability. A force-stopped
package remains an exceptional user-disabled state; merely recovering files on
the next manual launch is the only claim this spike may make.

## 8. Analysis and review

For each session run:

```bash
./scripts/analyze_session.sh exported_session.zip results/<run-id>
```

Check that the command exits 0; inspect `analysis_results.json`,
`stream_statistics.csv`, and `delivered_rates.svg`. Preserve anomalies in raw
order. Complete this matrix:

| Device/run | A | B | C | D subtests | Hash valid | Accel/gyro criteria | Screen-off | Battery/thermal | Limitation | Candidate verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Older/low | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| Mid-tier | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| Current/high | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |

Return unmodified exported ZIPs, analyzer outputs, completed matrix/run sheets,
APK hash/build identity and incident notes. Physical tests skipped for lack of a
device remain skipped—not passed.
