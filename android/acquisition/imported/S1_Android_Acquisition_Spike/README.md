# S1 Android Sensor Acquisition and Timing Feasibility Spike

This disposable native Android logger answers a bounded question for SIH26168:
can declared phones supply coherent IMU and GNSS-family evidence, including
screen-off delivery, for later navigation work? It is **not** the production
application or estimator. It contains no ML, fusion, map matching, routing,
cloud service, Google Play services, OBD-II integration, raw pseudorange
positioning, or IO-VNBD data.

## Current verdict

`S1-PENDING-DEVICE-EVIDENCE`

The software and deterministic host fixture can be verified without a phone.
No physical recording is included, so compilation or synthetic tests cannot
make S1 pass.

## Pinned toolchain

| Item | Version |
| --- | --- |
| Android Gradle Plugin | 8.13.2 |
| Gradle wrapper | 8.13 |
| Kotlin Android plugin/compiler | 2.3.10 |
| Compile SDK | 36 |
| Target SDK | 36 |
| Minimum SDK | 28 |
| Android SDK Build Tools | 35.0.0 |
| Java toolchain | 17 |
| JUnit | 4.13.2 |
| AndroidX Test runner | 1.6.2 |
| AndroidX Test JUnit extension | 1.2.1 |
| AndroidX Test transitive coroutines core JVM | 1.7.1 |
| Python analyzer | Python 3.12, standard library only |

Every direct dependency is version-pinned and resolved transitive versions are
frozen in `app/gradle.lockfile`. The Android app has no required network or
Google Play services dependency.

## Build and test

Install JDK 17, Android SDK Platform 36, and Build Tools 35.0.0. Then run:

```bash
./gradlew test
./gradlew lint
./gradlew assembleDebug
./gradlew assembleDebugAndroidTest
./scripts/run_host_tests.sh
```

Or run all checks and deterministic fixture analysis:

```bash
./scripts/run_all.sh
```

The debug APK is written under `app/build/outputs/apk/debug/`. Install it with
`adb install -r app/build/outputs/apk/debug/app-debug.apk`.

## Recording and export

1. Open the app, grant fine location (and notifications on API 33+), and press
   **Start Recording** while the activity is visible.
2. Execute exactly one declared protocol test per session.
3. Return to the app or use the notification action and press **Stop**.
4. Press **Export Latest Complete Session** and choose a local destination.

No collection occurs before Start. Sessions stay in app-private storage until
explicit export. A session ZIP contains only its versioned JSONL chunks and
session manifest. See `docs/S1_Device_Test_Protocol.md` before collecting data.

## Analyze an exported session

```bash
./scripts/analyze_session.sh S1_session_UUID.zip analysis_output
```

Outputs are `analysis_results.json`, `stream_statistics.csv`, and
`delivered_rates.svg`. The analyzer reads records in evidence order and does
not sort, resample, interpolate, or modify them.

## Project map

- `app/`: native Kotlin logger and Android unit tests
- `analyzer/`: offline, read-only Python analyzer
- `fixtures/`: synthetic deterministic anomaly fixture; never device evidence
- `scripts/`: one-command test and analysis entry points
- `docs/`: data contract, protocol, safety assessment, and gate report
- `results/`: executed verification outputs
- `S1_ARTIFACT_MANIFEST_v1.json`: hashes for every delivered file

## Return package for final adjudication

Return every exported session ZIP, the completed device matrix and run sheet,
the analyzer output directory for every session, phone tier rationale, and any
incident notes. Do not edit raw JSONL or manifests. Do not include unrelated
personal recordings.
