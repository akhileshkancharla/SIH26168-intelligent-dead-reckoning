# WP-09.6 — Airplane-mode replay verification, v1

| Field | Value |
| --- | --- |
| Issue | #77 — [WP-09.6] Verify complete airplane-mode replay demonstration |
| Parent | #10 — WP-09 Offline navigation UI and honest telemetry |
| Register milestone | P3 — Classical and Evaluation |
| Owner / reviewer | R5 / @akhileshkancharla |
| Stack | WP-09.3 `07c636b` → WP-09.4 `a238fc9` → WP-09.5 `e369775` → WP-09.6 |
| Status | JVM, build, static containment and repository checks verified; device airplane-mode demonstration pending |

## Verification boundary

The deterministic replay UI is presentation-only. `ReplayNavigationViewModel` consumes replay/scientific outputs and never supplies display coordinates, layer toggles, camera state, health badges, or smoothed paths to C-07. The local MapLibre style entry point is `asset://map/style.json`; its sole base source is bundled `asset://map/local_roads.geojson`. The style has no glyph, sprite, tile, or remote URL descriptor. The app manifest removes transitive `INTERNET`, `ACCESS_NETWORK_STATE`, and `ACCESS_WIFI_STATE` permissions from the merged APK manifest. These are strong offline-containment controls, but JVM tests and manifest inspection alone do not prove that the MapLibre native renderer never attempts a socket or that a device frame renders successfully in airplane mode.

All test positions are synthetic equatorial coordinates near (0°, 0°). No private route, device log, credential, downloaded tile, or binary fixture is committed.

## Automated evidence

`AirplaneModeReplayVerificationTest` exercises four independent boundaries:

| Check | Synthetic input and transition | Required assertion |
| --- | --- | --- |
| Asset containment | Bundled style, GeoJSON, source manifest, runtime style URI | Style and source use `asset://`; no remote glyph/sprite/tile/URL descriptor; three inherited network permissions marked for removal; replay and attribution labels retained. |
| Outage continuity | Initial GNSS → simulated outage → continued scientific frames → covariance and ambiguous candidates → reacquisition | Playback timestamp advances; raw GNSS stops at the last trusted fix; scientific history remains unchanged; tether says “Separation from last trusted GNSS fix”; valid ellipse is bounded and overflow fails closed; top-K is at most three with one primary; display recovery decays toward the moving live scientific coordinate without rewriting scientific history. |
| Telemetry honesty | `FIX_3D` with satellite/DOP fields → simulated outage | Visible state is `OUTAGE_SIMULATED`; stale satellite, HDOP, and PDOP values are absent; trusted-fix age remains separately identified; alignment retains its ingested `AlignmentStatusV1` value; absent data defaults to `UNINITIALIZED`, null covariance, and no candidates. |
| Concurrent publication | Four worker threads append 40 synthetic scientific points while an earlier snapshot is retained | Atomic `StateFlow` updates retain all 42 points; prior snapshot and input mutations cannot alter history; published list rejects in-place mutation. This is a JVM concurrency test, not an Android main-thread rendering test. |
| Narrow disclosure hierarchy | Normal replay and `BLACKOUT_DR` states | JVM assertion checks `REPLAY` and `SIMULATED OUTAGE` are assigned to the pinned primary banner slots. The Compose instrumentation test measures both badges inside a 320dp viewport in normal/outage states; its device execution remains pending. |

### Narrow-screen governance banner

`GovernanceFrame` no longer places mandatory disclosures in a horizontal-scroll row. Its first, fixed-width tier pins `REPLAY` and, during outage, `SIMULATED OUTAGE` in weighted slots. A second full-width tier retains `SOURCE: DETERMINISTIC_REPLAY`; the final tier retains `DEMO` and `REPLAY MODE`. The primary tier is rendered before secondary metadata, so the long source string cannot push the replay/outage warnings into an undiscovered scroll offset. The 320dp Compose instrumentation test checks rendered visibility and horizontal containment for both states. This test must execute on a connected device/emulator before it is marked passed.

Local Gradle 8.9 execution with `--no-daemon` and build output outside OneDrive: `:app:testDebugUnitTest :app:lintDebug :app:compileDebugAndroidTestKotlin` and `:app:assembleDebug` — **BUILD SUCCESSFUL**; 51 JVM tests passed and the two Compose instrumentation assertions compiled. The merged debug manifest and `aapt dump permissions` on the packaged APK contain no `INTERNET`, `ACCESS_NETWORK_STATE`, or `ACCESS_WIFI_STATE` permission. The local debug APK SHA-256 is `c1e5c2a75e220a21a747598e486431087098d688c72c56aa5c08e9b39c6fd313` (local build evidence, not a committed binary). The MapLibre style and local road asset checks pass in the JVM suite.

Graphify 0.9.53 sanitized snapshot verification passed (2,861 nodes, 4,823 edges, 195 communities). `python ci/verify_repository.py all` and `forbidden`, `python ci/generate_contract_bindings.py --check`, and `git diff --check` passed. The bootstrap suite completed 57 tests with one expected skip and no failures. These are local results; current-head remote CI must run after push.

## Required device airplane-mode acceptance run

An Android device/emulator was not connected for this verification revision. Before declaring Issue #77 fully demonstrated, install the final debug APK on a device, switch on airplane mode in Android Settings, verify Wi-Fi and mobile data remain disabled, and then execute the ten authoritative events from `SIH26168_Demo_Architecture_v1.md` in sequence. Capture screen video, timestamps, and a filtered network/traffic trace from before app launch through after-run summary. Do not use a screenshot or stale cache as proof of local rendering. Record the APK SHA-256, device/API level, fixture hash, and evidence locations.

| Event | Device observation / evidence gate |
| --- | --- |
| 1 — GNSS-aided start | Local road map and route visible; scientific puck and uncertainty labelled; `SOURCE: DETERMINISTIC_REPLAY`, `REPLAY MODE`, `DEMO`, and `© OpenStreetMap contributors` remain visible. |
| 2 — outage begins | `SIMULATED OUTAGE` appears; raw GNSS freezes at the trusted anchor; no network dependency or UI stall. |
| 3 — output continues | Replay timestamps and scientific updates continue at the fixture-defined rate; no fabricated output-rate claim. |
| 4 — inertial estimate continues | Scientific trace advances separately from any display-smoothed or withheld trace. |
| 5 — turn during outage | Route and scientific trace remain distinct; amber tether is labelled separation, never measured drift. |
| 6 — uncertainty grows | Display only valid configuration-derived covariance geometry; invalid/non-finite data suppresses the ellipse. |
| 7 — candidates | Show at most one primary and two alternatives only when supplied and status permits; unavailable matcher evidence stays unavailable. |
| 8 — biased fix rejected | No first-fix privilege; rejection must come from evidenced NIS/dwell inputs, not a UI simulation. |
| 9 — credible fix accepted | Acceptance and state transition must come from evidenced upstream replay/scientific output. |
| 10 — recovery and summary | Display recovery converges to the moving scientific position; scientific history and C-07 metrics remain untouched; reference/withheld data is evaluation-only. |

**Pass criteria:** The actual local map, route, overlays, labels, attribution, controls, and health HUD remain responsive for the complete airplane-mode run; no external request or socket attempt is observed; all ten fixture event transitions are evidenced; the app does not crash or stall. If map initialization fails, the UI must report unavailable map state without an online fallback or fabricated geometry. A failed/missing runtime-matcher, S3, S4, or renderer capability must be labelled `UNAVAILABLE` or `EXPERIMENTAL/SHADOW` as applicable, not replaced with synthetic confidence.

**Current limitation:** The JVM suite validates deterministic state and bundled inputs, and the build verifies the merged manifest. The Compose 320dp instrumentation assertion is compiled but cannot execute without a connected device/emulator. Neither the JVM suite nor compilation executes MapLibre native rendering, radio isolation, socket tracing, or the complete ten-event device sequence. Those acceptance observations remain open until a device run is attached to Issue #77 / its PR. Consequently this document is verification preparation and offline contract evidence, not a claim of completed end-to-end airplane-mode demonstration.
