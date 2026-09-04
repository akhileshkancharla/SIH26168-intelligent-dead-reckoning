# SIH26168 WP-09.7 Submission UI Wireframes and Screen-State Inventory v1

**Issue:** [#78 — WP-09.7 Produce submission UI wireframes and screen-state inventory](https://github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning/issues/78)  
**Parent:** [#10 — WP-09 Offline navigation UI and honest telemetry](https://github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning/issues/10)  
**Milestone:** M1 — Submission Contracts  
**Owner:** R5 — Android/frontend  
**Reviewer:** @akhileshkancharla  
**Status:** UI contract; this document does not claim Android renderer or runtime-feature completion

## 1. Purpose and authority

This document defines the submission-facing Android UI contract for WP-09. It provides the screen map, navigation hierarchy, ten-event demonstration wireframes, screen-state inventory, honest-telemetry rules, accessibility requirements, and acceptance traceability required before Compose implementation.

The normative sources, in descending order of authority, are:

1. `SIH26168_High_Level_Architecture_Revision3.md`.
2. `SIH26168_Development_Design_Baseline_v1.md`.
3. `SIH26168_Interface_Inventory_v1.md`, especially I-07, I-08, I-11, and I-13 through I-17.
4. `SIH26168_Demo_Architecture_v1.md`.
5. WP-09 acceptance: airplane-mode replay shows the local map, traces, uncertainty, candidates, mandatory mode labels, and visible attribution.

This is a presentation contract, not implementation evidence. It does not establish that Android map rendering, runtime map matching, S3 alignment, S4 learned inference, field-route validation, or drift targets have passed.

## 2. Non-negotiable scientific-integrity rules

1. `LIVE_DEVICE` and `DETERMINISTIC_REPLAY` are distinct source modes and are always visible while a run is open.
2. `DEMO` is a separate persistent badge for a demonstration run.
3. `SIMULATED OUTAGE` is a separate persistent badge for every interval controlled by a software scenario mask. It must not be replaced by a generic GNSS-loss icon.
4. OpenStreetMap attribution is permanently visible whenever the map is visible, including full-screen map, split panel, paused replay, errors, and after-run views.
5. Scientific, display, reference/withheld, route, and candidate geometry use distinct labels and visual encodings. Colour alone is insufficient.
6. Display interpolation or smoothing is derived presentation only. It is never used for metrics, labelled as the scientific estimate, or fed into C-07.
7. Withheld/reference GNSS remains evaluation-only during outage and never appears as an estimator input.
8. C-07 remains the only owner of navigation state and covariance. Map and learned outputs are proposals; neither overwrites the scientific trace.
9. A returning GNSS fix receives no first-fix privilege. Screening, rejection, dwell, and acceptance evidence remain visible.
10. Missing or unevidenced functionality is shown as `UNAVAILABLE`; provisional functionality may be shown as `EXPERIMENTAL`. No plausible substitute data is fabricated.
11. A stale or invalid scientific state is not silently held and shown as current. Its age and invalid/fault state are visible.
12. Network connectivity is not a proxy for GNSS, map, or navigation health. The navigation path remains offline-first.

## 3. Information architecture

### 3.1 Screen map

```text
Application
|
+-- Launch / Readiness
|   +-- Capability and manifest checks
|   +-- Permission explanation
|   +-- Source selection
|       +-- LIVE_DEVICE
|       `-- DETERMINISTIC_REPLAY
|
+-- Run Workspace
|   +-- Map and Route (default)
|   |   +-- Scientific trace
|   |   +-- Display trace
|   |   +-- Optional reference/withheld trace
|   |   +-- Uncertainty ellipse/band
|   |   `-- Top-K candidate overlay
|   +-- Health
|   |   +-- Sensor
|   |   +-- GNSS
|   |   +-- Navigation
|   |   +-- Alignment
|   |   +-- Model
|   |   +-- Map
|   |   +-- Reacquisition
|   |   `-- Recording
|   +-- Timeline
|   |   +-- Outage events
|   |   +-- Reacquisition decisions
|   |   `-- Mode transitions
|   +-- Candidates
|   |   +-- Top-K scores
|   |   +-- Entropy and margin
|   |   `-- Map version and abstention reason
|   `-- Evidence details
|       +-- State/evidence IDs
|       +-- Scenario/mask ID
|       +-- Configuration/build IDs
|       `-- Output-rate and gap evidence
|
`-- After-run Report
    +-- Endpoint error
    +-- Maximum error
    +-- RMSE
    +-- Transition summary
    +-- Output-rate summary
    +-- Recording completeness
    `-- Export evidence
```

### 3.2 Primary navigation

The run workspace uses four destinations: **Map**, **Health**, **Timeline**, and **Candidates**. The source, demo, and simulated-outage badges sit above destination content and therefore survive navigation. Run controls are contextual: live sessions expose start/stop recording; replay exposes play/pause, restart, and speed. Seeking, if implemented, creates a new run identity according to I-17 and must warn before execution.

The after-run report is entered only after a controlled stop or completed replay. Back returns to the stopped run workspace without mutating evidence. Starting another run returns through readiness checks and creates a new scientific run identity.

### 3.3 Persistent application frame

```text
+----------------------------------------------------------------------------+
| SIH26168  [SOURCE: DETERMINISTIC_REPLAY] [DEMO] [SIMULATED OUTAGE]         |
| Run: <short run ID>  t=<session elapsed>  Scientific age: <milliseconds>   |
+----------------------------------------------------------------------------+
|                                                                            |
|                        active destination content                          |
|                                                                            |
+----------------------------------------------------------------------------+
| Map | Health | Timeline | Candidates             © OpenStreetMap contributors|
+----------------------------------------------------------------------------+
```

Badge text must remain present; icons and colour are supplementary. `SIMULATED OUTAGE` is displayed only while the software mask is active, while `DEMO` and the selected source mode persist for the run. On compact screens badges may wrap, but must not collapse into an unlabeled icon.

## 4. Visual language and data separation

| Layer | Required label | Suggested visual encoding | Integrity rule |
| --- | --- | --- | --- |
| Scientific estimate | `SCIENTIFIC` | Solid line with position marker | Direct I-07 state only; validity and age shown. |
| Display position | `DISPLAY (SMOOTHED)` | Dashed line | Derived for visual continuity; excluded from metrics and C-07. |
| Reference/withheld | `REFERENCE — WITHHELD` | Dotted line with lock symbol | Optional; evaluation-only and not estimator input during outage. |
| Route | `ROUTE` | Wide translucent corridor | Must not imply field validation when route status is pending. |
| Uncertainty | `95% UNCERTAINTY` or configured confidence | Hatched ellipse/band | Computed from I-08; confidence definition must be configured, not assumed. |
| Map candidates | `CANDIDATE 1..K` | Numbered parallel strokes | Proposal only; never relabelled as scientific state. |

The final palette is selected during Compose accessibility implementation. Every line must also differ by pattern, marker, label, or width, and meet the applicable contrast target.

## 5. Ten-event demonstration wireframes

The wireframes are logical layouts, not pixel specifications. `<value>` denotes runtime data rather than placeholder UI copy. When evidence is absent, the UI displays the specified unavailable state instead of inventing a value.

### Event 1 — Valid GNSS-aided start and anchor

```text
+----------------------------------------------------------------------------+
| SIH26168 [SOURCE: DETERMINISTIC_REPLAY] [DEMO]                              |
| GNSS_AIDED | GNSS HEALTHY | anchor <evidence ID> | +/- <uncertainty> m      |
+-----------------------------------------------+----------------------------+
| LOCAL MAP / ROUTE                             | HEALTH                     |
|                                               | Sensor      AVAILABLE      |
|   route ===============================       | GNSS        HEALTHY        |
|                   [S] scientific anchor       | Navigation  GNSS_AIDED     |
|                 (<confidence> uncertainty)    | Alignment   UNINITIALIZED  |
|                                               | Model       DISABLED       |
| Legend: [S] SCIENTIFIC  == ROUTE              | Map         <actual state> |
+-----------------------------------------------+----------------------------+
| Provider <provider> | state <sequence> | fix <evidence ID>                 |
| Map | Health | Timeline | Candidates             © OpenStreetMap contributors|
+----------------------------------------------------------------------------+
```

Evidence: provider, fix/evidence ID, source mode, I-07 state sequence, I-08 uncertainty, and anchor/origin identity. If the map is not verified, the map panel shows `MAP UNAVAILABLE` while the textual scientific state remains visible.

### Event 2 — Deliberate GNSS outage begins

```text
+----------------------------------------------------------------------------+
| SIH26168 [SOURCE: DETERMINISTIC_REPLAY] [DEMO] [SIMULATED OUTAGE]           |
| BLACKOUT_DR | GNSS UNAVAILABLE | outage began t=<time>                     |
+-----------------------------------------------+----------------------------+
| LOCAL MAP / ROUTE                             | OUTAGE EVIDENCE            |
|   reference ............. [LOCKED/WITHHELD]   | Type SOFTWARE_SIMULATED    |
|   scientific ---------[S]                     | Scenario <scenario ID>     |
|                 ( uncertainty )               | Mask <mask ID>             |
|                                               | Hidden <field list>        |
| Raw GNSS retained as separate evidence; not estimator input                |
+----------------------------------------------------------------------------+
| Timeline |-- GNSS aided --| OUTAGE >>>                                  |
| Map | Health | Timeline | Candidates             © OpenStreetMap contributors|
+----------------------------------------------------------------------------+
```

The badge, scenario ID, mask ID, and hidden-field list distinguish a controlled visibility mask from natural GNSS loss. Retained raw/reference evidence is explicitly separated from inference.

### Event 3 — Approximately 10 Hz output continues

```text
+----------------------------------------------------------------------------+
| SIH26168 [SOURCE: DETERMINISTIC_REPLAY] [DEMO] [SIMULATED OUTAGE]           |
| BLACKOUT_DR | Scientific output ACTIVE | target approximately 10 Hz        |
+-----------------------------------------------+----------------------------+
| SCIENTIFIC TRACE                              | OUTPUT EVIDENCE            |
|  s1--s2--s3--s4--s5--s6--s7--s8--s9--[S]     | Observed <rate> Hz         |
|  each point = accepted I-07 state             | p50 dt <value> ms          |
|                                               | p95 dt <value> ms          |
|                                               | Gaps <count>               |
|                                               | Last seq <sequence>        |
+-----------------------------------------------+----------------------------+
| Reduced cadence is reported, never hidden; UI refresh is not core rate.     |
| Map | Health | Timeline | Candidates             © OpenStreetMap contributors|
+----------------------------------------------------------------------------+
```

The panel reports observed intervals and gaps. “Approximately 10 Hz” is not displayed as a pass unless measured output evidence supports it. UI frame rate is never substituted for scientific output rate.

### Event 4 — Inertial scientific estimate continues

```text
+----------------------------------------------------------------------------+
| SIH26168 [SOURCE: DETERMINISTIC_REPLAY] [DEMO] [SIMULATED OUTAGE]           |
| BLACKOUT_DR | GNSS UNAVAILABLE | SCIENTIFIC VALID                          |
+-----------------------------------------------+----------------------------+
| LOCAL MAP                                     | SCIENTIFIC STATE           |
| anchor [A]-------previous------current [S]     | Sequence <sequence>        |
|                         ( uncertainty )        | Epoch <monotonic epoch>    |
|                                               | Propagation C-07           |
| [S] SCIENTIFIC; no held GNSS marker           | Validity <validity>        |
|                                               | Sensor <actual state>      |
+-----------------------------------------------+----------------------------+
| Trace source: I-07 | covariance: I-08 | GNSS updates masked                 |
| Map | Health | Timeline | Candidates             © OpenStreetMap contributors|
+----------------------------------------------------------------------------+
```

If mandatory accelerometer or gyroscope input is missing, the UI transitions to `FAULT`, invalidates the scientific output, and retains diagnostics. It must not animate an extrapolated position as valid scientific navigation.

### Event 5 — Route turn during outage

```text
+----------------------------------------------------------------------------+
| SIH26168 [SOURCE: DETERMINISTIC_REPLAY] [DEMO] [SIMULATED OUTAGE]           |
| BLACKOUT_DR | TURN IN OUTAGE                                                |
+-----------------------------------------------+----------------------------+
| LOCAL MAP / ROUTE                             | TRACE LEGEND               |
| route ===========+                            | ---- SCIENTIFIC            |
|                  |                            | - -  DISPLAY (SMOOTHED)    |
| scientific ------+---[S]                      | .... REFERENCE — WITHHELD  |
| display - - - - -+ -[D]                       | ==== ROUTE                 |
| reference .......+....[R lock]                 |                            |
+-----------------------------------------------+----------------------------+
| Reference is evaluation-only; display output is excluded from metrics/C-07.|
| Map | Health | Timeline | Candidates             © OpenStreetMap contributors|
+----------------------------------------------------------------------------+
```

The separation remains understandable without colour. If reference disclosure is disabled, its line and legend item are absent rather than shown as zero or coincident with the estimate.

### Event 6 — Computed uncertainty grows

```text
+----------------------------------------------------------------------------+
| SIH26168 [SOURCE: DETERMINISTIC_REPLAY] [DEMO] [SIMULATED OUTAGE]           |
| BLACKOUT_DR | UNCERTAINTY GROWING                                           |
+-----------------------------------------------+----------------------------+
| LOCAL MAP                                     | UNCERTAINTY                |
| earlier (---)                                 | Source I-08                |
|       scientific trail ---------[S]            | Confidence <configured>    |
|                              (((     )))       | Major axis <value> m       |
|                      (( <CONFIDENCE> BAND ))   | Minor axis <value> m       |
|                              (((     )))       | Quality <flags>            |
+-----------------------------------------------+----------------------------+
| If covariance is nonfinite/dimension-invalid: SCIENTIFIC FAULT, no ellipse. |
| Map | Health | Timeline | Candidates             © OpenStreetMap contributors|
+----------------------------------------------------------------------------+
```

The UI visualizes the actual I-08 covariance associated with the displayed I-07 sequence. It does not clip or replace an invalid covariance to create a visually reassuring ellipse.

### Event 7 — Top-K map candidates appear

```text
+----------------------------------------------------------------------------+
| SIH26168 [SOURCE: DETERMINISTIC_REPLAY] [DEMO] [SIMULATED OUTAGE]           |
| MAP AMBIGUOUS | CANDIDATES ARE PROPOSALS | scientific state unchanged      |
+-----------------------------------------------+----------------------------+
| LOCAL MAP                                     | TOP-K CANDIDATES           |
| road A =======  [1]                           | 1 edge <id> score <value>  |
| scientific ----[S]                            | 2 edge <id> score <value>  |
| road B =======  [2]                           | 3 edge <id> score <value>  |
|                                               | Entropy <value>            |
| No candidate overwrites [S].                  | Margin <value>             |
|                                               | Map version <version>      |
+-----------------------------------------------+----------------------------+
| Status AMBIGUOUS / ABSTAIN; feedback <OFF or EXPERIMENTAL>                  |
| Map | Health | Timeline | Candidates             © OpenStreetMap contributors|
+----------------------------------------------------------------------------+
```

Until the runtime matcher is implemented and evidenced, this panel instead reads `TOP-K MATCHER — UNAVAILABLE` and exposes no fabricated candidates. If experimental output exists, it carries an `EXPERIMENTAL` label. Empty, version-mismatched, and ambiguous results remain unmatched.

### Event 8 — Deliberately biased returning fix is rejected

```text
+----------------------------------------------------------------------------+
| SIH26168 [SOURCE: DETERMINISTIC_REPLAY] [DEMO] [SIMULATED OUTAGE]           |
| REACQUIRING | RETURNING FIX REJECTED | scientific state unchanged          |
+-----------------------------------------------+----------------------------+
| LOCAL MAP                                     | REACQUISITION EVIDENCE     |
| scientific --------[S]                        | Phase SCREENING            |
|                         x rejected fix         | Fix <evidence ID>          |
|                                               | NIS <value>                |
| No jump to x                                  | Gate <threshold/config>    |
|                                               | Reason <typed reason>      |
+-----------------------------------------------+----------------------------+
| Timeline | OUTAGE >>> | x REJECTED | remain BLACKOUT_DR/REACQUIRING         |
| Map | Health | Timeline | Candidates             © OpenStreetMap contributors|
+----------------------------------------------------------------------------+
```

The biased fixture remains visibly simulated/fixture evidence. Rejection consumes the evidence ID once and causes no C-07 update. A missing NIS before computation is shown as `PENDING`, not zero.

### Event 9 — Subsequent credible fix is accepted

```text
+----------------------------------------------------------------------------+
| SIH26168 [SOURCE: DETERMINISTIC_REPLAY] [DEMO]                              |
| REACQUIRING -> GNSS_AIDED | CREDIBLE FIX ACCEPTED                           |
+-----------------------------------------------+----------------------------+
| LOCAL MAP                                     | REACQUISITION EVIDENCE     |
| scientific before -----[S]                    | Phase ACCEPTED             |
|                           + accepted update    | Fix <evidence ID>          |
| display - - - - - - - -[D]                    | Dwell <count>/<required>   |
|                                               | Consistency <evidence>     |
|                                               | Scientific jump <value> m  |
+-----------------------------------------------+----------------------------+
| Timeline | rejected | SCREENING | DWELL | ACCEPTED | GNSS_AIDED             |
| Map | Health | Timeline | Candidates             © OpenStreetMap contributors|
+----------------------------------------------------------------------------+
```

`SIMULATED OUTAGE` disappears only when the configured mask interval ends. Acceptance is supported by dwell/consistency and the C-07 update record; it is never inferred merely because a marker approaches the route.

### Event 10 — Smooth display recovery and after-run comparison

```text
+----------------------------------------------------------------------------+
| SIH26168 [SOURCE: DETERMINISTIC_REPLAY] [DEMO] | RUN COMPLETE               |
+-----------------------------------------------+----------------------------+
| TRACE COMPARISON                              | AFTER-RUN SUMMARY          |
| scientific -----------+------[S]               | Endpoint error <value> m   |
| display - - - - - - - + - -[D]                | Maximum error <value> m    |
| reference ............+......[R]                | RMSE <value> m             |
|                                               | Transitions <summary>      |
| DISPLAY (SMOOTHED), excluded from metrics     | Output rate <distribution> |
+-----------------------------------------------+----------------------------+
| Recording <COMPLETE/INCOMPLETE> | Evidence <run/config/build IDs>           |
| [View timeline] [View evidence] [Export, if eligible]                       |
|                                              © OpenStreetMap contributors   |
+----------------------------------------------------------------------------+
```

Endpoint, maximum, and RMSE metrics are calculated from scientific and eligible reference data only. Missing or ineligible reference evidence yields `NOT COMPUTABLE` with a reason. A smooth display transition is reported separately and never used to improve the scientific metrics.

## 6. Full screen-state inventory

Each state is observable and testable. Orthogonal health axes may change without forcing unrelated axes to healthy or failed states.

| State ID | Trigger | Allowed actions | Visible UI | Exit criteria | Degraded/error fallbacks |
| --- | --- | --- | --- | --- | --- |
| UI-00 LAUNCH_CHECKS | App launch or new-run request. | View check details; retry; leave. | Build/config/capability check progress; no run claims. | Required manifests, configuration, and mandatory capabilities validate. | Invalid/unknown configuration blocks scientific start with typed reason. |
| UI-01 PERMISSION_REQUIRED | Required Android permission is absent. | Open system permission flow; retry; leave. | Plain-language purpose and exact missing capability. | Required permissions granted, or user returns to idle. | Denial remains idle; no fake sensor/GNSS availability. |
| UI-02 SOURCE_SELECTION | Readiness checks pass and no run is active. | Select `LIVE_DEVICE` or verified `DETERMINISTIC_REPLAY`; inspect scenario. | Source choices, capability status, replay manifest status. | Selected source validates and start is confirmed. | Corrupt/incomplete replay is rejected for normal demo; diagnostic inspection is labelled. |
| UI-03 LIVE_READY | Valid live source selected. | Start run; return to source selection. | Persistent `SOURCE: LIVE_DEVICE`; sensor/GNSS readiness; demo status. | New live session successfully starts. | Missing mandatory sensors block valid scientific navigation. |
| UI-04 REPLAY_READY | Verified replay and scenario selected. | Start replay; change scenario/source. | Persistent `SOURCE: DETERMINISTIC_REPLAY`; `DEMO` when applicable; manifest/scenario IDs. | Replay-control start event is accepted. | Validation error blocks start and shows the failed manifest/chunk/config check. |
| UI-05 INITIALIZING | Session starts before valid anchored output. | Stop; inspect health/evidence. | `INITIALIZING`; sensor, recording, GNSS, alignment, model, and map states. | Valid anchor produces GNSS-aided output, or policy enters degraded/fault. | Timeout/failure is explicit; no moving trace without valid I-07. |
| UI-06 GNSS_AIDED | C-09/C-07 reports `GNSS_AIDED`. | Navigate panels; pause replay; stop. | Scientific marker/trace; uncertainty; provider and evidence IDs; `GNSS HEALTHY` or actual quality. | Quality/outage transition, stop, or fault. | Stale/rejected fixes transition through typed degraded state; no silent update. |
| UI-07 QUALITY_DEGRADED | Integrity hysteresis reports degraded GNSS or sensor quality. | Inspect reasons/timeline; stop; replay controls. | `DEGRADED`, reasons, state age, uncertainty, affected health axis. | Health recovers, blackout begins, or fault occurs. | Continue only where policy permits; scientific invalidity is shown immediately. |
| UI-08 SIMULATED_OUTAGE | A valid I-14 software mask begins. | Inspect scenario/mask; navigate panels; pause/stop replay. | Persistent `SIMULATED OUTAGE`; `BLACKOUT_DR`; scenario/mask/hidden-field evidence. | Mask ends and reacquisition policy advances, or run stops/faults. | Invalid mask is rejected; raw/reference evidence remains separate. |
| UI-09 NATURAL_OUTAGE | GNSS becomes unavailable without software mask. | Inspect reason; navigate; stop. | `GNSS UNAVAILABLE`; `BLACKOUT_DR`; no simulated badge. | GNSS candidate return, stop, or fault. | Never label natural/quality loss as simulated; connectivity remains independent. |
| UI-10 BLACKOUT_DR_VALID | C-07 propagates valid scientific states without GNSS updates. | Map/health/timeline/candidates; replay controls; stop. | Scientific trace, I-08 uncertainty, rate/gap evidence, GNSS unavailable. | Candidate return, GNSS recovery, stop, or fault. | Mandatory IMU loss causes fault; optional subsystem failure does not invent assistance. |
| UI-11 OUTPUT_RATE_DEGRADED | Measured state intervals/gaps depart from configured expectation. | Inspect rate evidence; stop. | Observed rate distribution, gaps, last sequence; degraded reason. | Rate returns within declared policy or run ends. | UI refresh rate is not substituted; throttling and shed features are disclosed. |
| UI-12 SCIENTIFIC_FAULT | I-07 invalidity, mandatory sensor loss, numeric failure, or invalid I-08. | Stop; inspect/export diagnostics if eligible. | `FAULT`; last valid state clearly historical; typed reason; no valid current marker. | Controlled stop and new-run readiness checks. | Display interpolation cannot conceal fault; evidence may continue diagnostically. |
| UI-13 ALIGNMENT_UNAVAILABLE | Alignment is `UNINITIALIZED`, `UNCERTAIN`, or not implemented. | Inspect health; continue classical eligible path. | Actual alignment state; dependent aids disabled. | Valid evidenced alignment or run end. | S3 not evidenced is `UNAVAILABLE`; no inferred vehicle alignment. |
| UI-14 ALIGNMENT_SLIP_SUSPECTED | C-05 reports `SLIP_SUSPECTED`. | Inspect reason; continue/stop. | Slip warning; alignment-dependent ML/NHC disabled. | Alignment becomes valid/uncertain or run ends. | Scientific propagation continues only through independent valid paths. |
| UI-15 MODEL_DISABLED | Run configuration sets model disabled. | Inspect configuration; continue. | `MODEL DISABLED`; classical-core label. | New run with a different validated configuration. | This is a complete baseline, not an error. |
| UI-16 MODEL_EXPERIMENTAL | Model is `SHADOW` or otherwise not eligible for production influence. | Inspect proposals/decisions; continue. | `EXPERIMENTAL` or `SHADOW`; terminal decision and reason. | New model state/config or run end. | Timeout/OOD/rejection leaves classical core unchanged. |
| UI-17 MODEL_FAILED | Model load/runtime validation fails. | Inspect reason; continue classical core; stop. | `MODEL FAILED`; typed failure; no implied correction. | New validated run/configuration. | Classical core continues; no fabricated learned output. |
| UI-18 MAP_AVAILABLE | Verified local display map loads. | Pan/zoom/recenter; inspect attribution; change panel. | Local map, map version, route status, permanent OSM attribution. | Map validation/render failure or run exit. | No implicit download; route marked pending where field validation is pending. |
| UI-19 MAP_UNAVAILABLE | Map is missing, corrupt, version-mismatched, or renderer unavailable. | Retry local load; inspect details; use health/timeline. | `MAP UNAVAILABLE`; textual scientific state and trace summary; reason. | Same-version verified map becomes available or run exits. | Navigation continues unmatched where valid; attribution is shown only if map content is displayed. |
| UI-20 MATCHER_UNAVAILABLE | Runtime matcher is absent/not evidenced/off. | Inspect status; continue unmatched. | `TOP-K MATCHER UNAVAILABLE` or `MAP MATCH OFF`; no candidate rows. | Evidenced same-version matcher output becomes available in an eligible build/run. | Never fabricate candidates or snap scientific state to road. |
| UI-21 MAP_NO_CANDIDATE | I-11 status is `NO_CANDIDATE`. | Inspect evidence; continue. | Empty candidate state, map version, reason; unmatched scientific trace. | Candidate result changes or run ends. | No nearest-road fallback. |
| UI-22 MAP_AMBIGUOUS | I-11 returns multiple candidates without clear gates. | Inspect Top-K details; continue. | Numbered candidates, scores, entropy, margin, `AMBIGUOUS/ABSTAIN`. | Gates produce `CLEAR`, no candidate, failure, or run end. | No constraint/overwrite; candidates remain proposals. |
| UI-23 MAP_CLEAR_EXPERIMENTAL | I-11 reports `CLEAR` in an evidenced experimental matcher. | Inspect details; continue. | Selected hypothesis plus all required score/version evidence; feedback state. | Result changes or run ends. | If map feedback is off, state that explicitly; scientific trace remains independently labelled. |
| UI-24 RETURN_SCREENING | A returning GNSS fix enters C-09 screening. | Inspect timeline/evidence; pause/stop replay. | `REACQUIRING`; fix ID; screening phase; pending/computed gate data. | Rejected, enters dwell, or run ends. | Missing values show `PENDING/UNAVAILABLE`, never zero. |
| UI-25 RETURN_REJECTED | Reacquisition evidence reports rejected. | Inspect reason; continue; stop. | `REJECTED`; NIS, gate, typed reason; unchanged scientific sequence/update status. | Another candidate arrives, outage continues, or run ends. | Remain DR/reacquiring; no first-fix update or visual jump. |
| UI-26 RETURN_DWELL | A credible candidate passes screening but policy requires consistency. | Inspect dwell evidence; continue; stop. | Dwell count/requirement, consistency evidence, current navigation mode. | Accepted, rejected/reset, or run ends. | Intermittent/inconsistent evidence resets/rejects per policy. |
| UI-27 RETURN_ACCEPTED | Dwell/consistency and C-07 gate accept a fix. | Inspect update; continue; stop. | `ACCEPTED`; evidence ID; scientific jump; transition evidence. | GNSS-aided mode stabilizes, another transition occurs, or run ends. | Acceptance cannot be inferred solely from display proximity. |
| UI-28 DISPLAY_RECOVERY | Scientific state has updated and presentation policy smooths display continuity. | Compare traces; navigate; stop. | Separate `SCIENTIFIC` and `DISPLAY (SMOOTHED)` traces; display policy. | Display transition completes or run ends. | Scientific state is never smoothed; display trace is excluded from metrics. |
| UI-29 RECORDING_DEGRADED | Recording reports evidence degradation or low storage. | Stop; inspect storage/evidence; continue visibly if policy permits. | `EVIDENCE_DEGRADED` or `LOW_STORAGE`; affected interval and claim limitation. | Recording recovers where supported or controlled stop occurs. | Never claim unrecorded intervals; finalize recoverable chunks. |
| UI-30 RECORDING_INCOMPLETE | Stop/recovery cannot produce a complete manifest. | Inspect details; export diagnostic data if permitted; start new run. | `INCOMPLETE`; loss/hash/completeness reasons. | New run or exit; status itself is immutable for the run. | Incomplete replay is diagnostic-only and cannot be a normal demo. |
| UI-31 RUN_COMPLETE | Controlled stop or replay completion finalizes evidence. | Open report/timeline/evidence; export if eligible; start new run. | Completion and recording status; run/config/build identities. | Report opened, new run starts, or app exits. | Drain failure transitions to incomplete and blocks unsupported claims. |
| UI-32 AFTER_RUN_REPORT | User opens the completed-run comparison. | Inspect traces/timeline/evidence; export; return. | Endpoint/max/RMSE, transitions, output-rate distribution, separate traces. | User returns or starts a new run. | Metrics without eligible reference data show `NOT COMPUTABLE` plus reason. |
| UI-33 REPLAY_PAUSED | Pause command is accepted. | Resume; restart; inspect panels; seek if implemented; stop. | Persistent replay/demo/outage badges; paused time and unchanged evidence. | Resume/restart/stop command accepted. | Seek creates a new run identity; invalid command is rejected visibly. |
| UI-34 STALE_PRESENTATION | I-16 snapshot age exceeds UI policy while scientific validity is not newly confirmed. | Inspect health; wait; stop. | `STALE`, exact age, last sequence; historical marker styling. | Fresh valid snapshot or fault/stop. | Never animate or relabel the stale position as current. |

## 7. Subsystem health and honest telemetry

### 7.1 Health axes

The Health destination presents every I-13 axis independently and includes the latest typed reasons. No aggregate green indicator may erase an unhealthy axis.

| Axis | Displayed states | Required accompanying evidence |
| --- | --- | --- |
| Sensor | `AVAILABLE`, `PARTIAL`, `GAP`, `MISSING_MANDATORY`, `FAILED` | Affected stream, gap/loss counters, delivered/accepted rate, thermal/resource reason where available. |
| GNSS | `HEALTHY`, `DEGRADED`, `UNAVAILABLE`, `CANDIDATE_RETURN` | Provider, fix age, evidence ID, integrity reason; connectivity is not shown as GNSS health. |
| Navigation | `INITIALIZING`, `GNSS_AIDED`, `DEGRADED`, `BLACKOUT_DR`, `REACQUIRING`, `FAULT` | I-07 sequence/epoch/validity, transition time, typed reason. |
| Alignment | `UNINITIALIZED`, `VALID`, `UNCERTAIN`, `SLIP_SUSPECTED` | Status/observability and dependent-aid eligibility; `UNAVAILABLE` presentation while S3 is unevidenced. |
| Model | `DISABLED`, `LOADING`, `SHADOW`, `ELIGIBLE`, `REJECTED`, `FAILED` | Model/config identity when present, proposal decision and reason; S4 presented as `EXPERIMENTAL` unless evidenced otherwise. |
| Map | `MISSING`, `NO_CANDIDATE`, `AMBIGUOUS`, `CLEAR`, `FAILED` | Map version/hash identity, renderer state, candidate status; runtime matcher unavailable until evidenced. |
| Reacquisition | `IDLE`, `SCREENING`, `DWELL`, `ACCEPTED`, `REJECTED` | Fix ID, NIS/gate when computed, dwell, acceptance and scientific jump. |
| Recording | `STARTING`, `HEALTHY`, `EVIDENCE_DEGRADED`, `LOW_STORAGE`, `INCOMPLETE`, `COMPLETE` | Queue/loss/storage status, manifest/chunk completeness, affected intervals. |
| Source/demo | `LIVE_DEVICE` or `DETERMINISTIC_REPLAY`; independent `DEMO`; independent `SIMULATED OUTAGE` | Source adapter, run/scenario/mask identity and replay verification status. |

### 7.2 Status-component contract

Each status component contains visible text, an icon/shape, severity semantics, state age, and an accessible description. Unknown values render as `UNKNOWN`, never healthy. Detail views expose reason codes and evidence IDs without placing raw precise location in ordinary diagnostic logs.

Severity summary is limited to prioritization:

- **Fault:** scientific output invalid or start blocked.
- **Degraded:** output/recording remains available with a disclosed limitation.
- **Attention:** a proposal is ambiguous, experimental, screening, or pending.
- **Nominal:** that specific axis is healthy; it says nothing about other axes.
- **Unavailable:** optional or unevidenced capability supplies no result.

### 7.3 Offline and map failure behaviour

Airplane mode must not initiate a download. The verified local map and route remain usable without network access. If local map validation or rendering fails, the UI retains textual scientific state, uncertainty values, timeline, and health while showing `MAP UNAVAILABLE`. It never substitutes an online map, cached screenshot, fabricated route, or map-matched position.

### 7.4 After-run metric contract

The report states the compared trace pair, eligible interval, units, sample count, reference provenance, and configuration/build identity. Endpoint error, maximum error, and RMSE use scientific estimates only. Display-path continuity may have separate presentation statistics but cannot enter scientific error metrics. Missing, withheld, invalid, or time-incompatible reference evidence yields `NOT COMPUTABLE` with a typed reason. Output rate is a measured distribution with gap count, not a hard-coded label.

## 8. Interaction, accessibility, and responsive behaviour

1. Status, trace, and candidate meaning must not rely on colour alone.
2. Badge and status text remains readable at Android font scaling; wrapping is preferred to truncating integrity labels.
3. Touch targets meet the platform accessibility minimum used by the Android module.
4. TalkBack descriptions announce layer identity before value, for example “Scientific position, valid, age 80 milliseconds.”
5. Dynamic updates use restrained live-region announcements. Critical mode changes, outage start, rejected return, accepted return, fault, and recording degradation are announced; 10 Hz position updates are not.
6. Map gestures have non-gesture alternatives for recenter and zoom where required.
7. When space is constrained, the map and selected detail panel stack vertically. Persistent badges and attribution remain visible.
8. Landscape/tablet layouts may use the shown split view. Portrait uses the same information hierarchy, not a reduced-integrity variant.
9. Screenshots used for submission must contain no private route, raw private coordinates, personal identifiers, or secrets.

## 9. Acceptance-criteria traceability

| Requirement | Source | Design evidence in this document | Planned verification |
| --- | --- | --- | --- |
| Produce submission UI wireframes. | Issue #78 | Sections 3–5 define the navigation hierarchy, persistent frame, and all ten event wireframes. | Documentation review; later Compose screenshot tests. |
| Produce a screen-state inventory. | Issue #78 | Section 6 defines triggers, actions, visible UI, exit criteria, and fallbacks for UI-00 through UI-34. | Contract review against implementation state reducers/tests. |
| Airplane-mode replay shows a local map and route. | Parent #10 / WP-09 | UI-04, UI-18, Section 7.3, and all map event frames define verified local-map behaviour without network fallback. | Android airplane-mode device/instrumentation test. |
| Show distinct traces. | Parent #10 / WP-09 | Section 4 and Events 2, 5, and 10 separate scientific, display, optional reference/withheld, route, and candidates. | Screenshot and semantic/accessibility tests. |
| Show uncertainty. | Parent #10 / WP-09 | Event 6 and UI-10 bind the ellipse/band to I-08 and its I-07 state sequence. | Covariance fixture screenshot; invalid-covariance fault test. |
| Show candidates and honest matcher status. | Parent #10 / WP-09 | Event 7 and UI-20 through UI-23 define Top-K, scores, entropy, margin, version, ambiguity, abstention, and unavailable state. | Empty/ambiguous/version-mismatch fixtures; no candidates until matcher evidence exists. |
| Show mandatory mode labels. | Parent #10 / WP-09 and demo architecture | Sections 2–3 make source mode, `DEMO`, and `SIMULATED OUTAGE` persistent and independent. | Screenshot matrix across destinations, pause, outage, errors, and report. |
| Keep attribution visible. | Parent #10 / WP-09 | Persistent frame and every map-bearing wireframe show `© OpenStreetMap contributors`. | Screenshot/accessibility test in portrait/landscape and airplane mode. |
| Show all ten demonstration events. | Demo architecture | Section 5 maps one wireframe to each authoritative event in order. | Deterministic replay golden sequence and storyboard review. |
| Show subsystem health and honest telemetry. | Parent #10; I-13/I-16 | Sections 6–7 preserve orthogonal axes, state age, reasons, and evidence identity. | State-transition unit tests and accessibility assertions. |
| Do not feed display smoothing into science/metrics. | Architecture Revision 3 | Sections 2, 4, Event 10, UI-28, and Section 7.4 separate derived display from C-07 and metrics. | Reducer/data-lineage tests and report fixture. |
| Do not fabricate unimplemented modules. | Demo truth table | Event 7, UI-13, UI-16, and UI-20 require `UNAVAILABLE`/`EXPERIMENTAL` for unevidenced S3/S4/matcher/renderer capability. | Capability-off screenshots and absence-of-data assertions. |
| Reject biased return; accept only credible return. | Demo events 8–9; I-15 | Events 8–9 and UI-24 through UI-27 display screening, NIS/gate/reason, dwell, rejection, acceptance, and scientific jump. | Biased/good/intermittent reacquisition fixtures. |
| Show after-run comparison honestly. | Demo event 10 | Event 10, UI-32, and Section 7.4 define eligible metrics, transitions, rate distribution, and `NOT COMPUTABLE`. | Analyzer/report parity test with and without eligible reference. |

## 10. Implementation handoff

This contract informs the following submission-critical issues without implementing them:

- #72 / WP-09.1: Compose navigation shell implements the hierarchy and persistent application frame.
- #73 / WP-09.2: MapLibre local renderer implements offline map behaviour and permanent attribution.
- #74 / WP-09.3: trajectory layers implement the scientific/display/reference/candidate separation.
- #76 / WP-09.5: health UI implements the independent axes, reasons, state age, and mandatory badges.
- #112 / WP-15.7: demo storyboard follows the ten event frames and truth classifications.

Before implementation, the screen model must consume I-16 as a read-only latest-wins presentation snapshot. Compose state must not mutate C-07, fabricate absent interface fields, infer health from visual movement, or send UI smoothing into scientific components. Exact typography, colour tokens, component dimensions, thresholds, and metric confidence levels remain implementation/configuration decisions and must not be invented from these wireframes.

## 11. Definition of done for WP-09.7

- The ten authoritative demo events each have a wireframe and evidence expectations.
- The navigation hierarchy covers readiness, run workspace, evidence detail, and after-run report.
- The state inventory defines nominal, degraded, unavailable, experimental, stale, and fault behaviour.
- Source, demo, simulated-outage, scientific/display/reference, and map-candidate semantics are explicit.
- Permanent OSM attribution is specified for every map-bearing state.
- Unevidenced Android renderer, matcher, S3, and S4 capabilities are not represented as complete.
- Requirements trace to Issue #78 and parent Issue #10.
- Repository verification passes after adding this Markdown file.

## 12. Review checklist

- [ ] Architecture owner confirms no UI path can write scientific state.
- [ ] Navigation owner confirms GNSS/outage/reacquisition terminology and transitions.
- [ ] Map owner confirms version, route-status, Top-K, ambiguity, and abstention presentation.
- [ ] Android owner confirms every state is representable in Compose without hidden inferred data.
- [ ] Reviewer confirms mandatory labels and attribution persist across every relevant screenshot.
- [ ] Reviewer confirms `UNAVAILABLE`/`EXPERIMENTAL` treatment matches current evidence status.
- [ ] Reviewer confirms display smoothing is excluded from C-07 and all scientific metrics.
- [ ] Reviewer confirms private route/location information is absent from submission assets.
