# SIH26168 WP-15.7 Demo Narrative and Storyboard v1

**Issue:** [#112 — WP-15.7 Define SIH submission demo narrative and storyboard](https://github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning/issues/112)
**Parent:** [#16 — WP-15 Ten-event deterministic demonstration](https://github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning/issues/16)
**Milestone:** M1 — Submission Contracts
**Assigned roles:** R5 — Android/frontend; R6 — verification/evidence
**Reviewer:** @akhileshkancharla
**Status:** submission narrative and storyboard contract; not implementation or scientific-validation evidence

## 1. Purpose and authority

This document defines the evaluator-facing narrative, visual sequence, evidence cues, and fallback language for the SIH26168 ten-event demonstration. It binds the submission story to the ten events in `SIH26168_Demo_Architecture_v1.md`, the interfaces in Architecture Revision 3, and the screen contract reviewed in WP-09.7.

The local issue register identifies Issue #16 as the WP-15 parent. Issue #15 belongs to WP-14 and is therefore not used as the parent reference here.

The governing sources, in order, are:

1. `SIH26168_High_Level_Architecture_Revision3.md`.
2. `SIH26168_Development_Design_Baseline_v1.md`.
3. `SIH26168_Interface_Inventory_v1.md`, especially I-07, I-08, I-11, and I-13 through I-17.
4. `SIH26168_Demo_Architecture_v1.md` and its exact ten-event sequence.
5. `SIH26168_WP09_7_Submission_UI_Wireframes_v1.md` at reviewed commit `3148da7`, including UI-00 through UI-34.

Architecture contracts describe intended behaviour; they do not prove that behaviour has been implemented or scientifically validated. At the current repository baseline, Android rendering, runtime map matching, S3 alignment, S4 learned correction, integrated live operation, and drift performance remain unevidenced or incomplete. The demonstration must show `UNAVAILABLE`, `EXPERIMENTAL`, or `SHADOW` wherever that remains true at rehearsal time.

## 2. Executive demonstration arc

### 2.1 One-sentence evaluator narrative

SIH26168 preserves an auditable scientific navigation estimate through a clearly labelled, software-simulated GNSS outage, exposes growing uncertainty and optional bounded map proposals without disguising them as truth, rejects an inconsistent returning fix, accepts only a credible return after evidence-based screening, and separates cosmetic display recovery from scientific metrics.

### 2.2 Beginning, tension, resolution

- **Beginning — establish trust (Events 1–2):** Anchor with valid GNSS evidence, then declare the controlled outage before hiding GNSS from the estimator. The evaluator sees the source, demo, and simulated-outage labels rather than being asked to infer them.
- **Tension — remain useful without overstating certainty (Events 3–7):** Scientific output and inertial propagation continue through a turn while computed uncertainty grows. Any map hypotheses remain numbered proposals; an absent runtime matcher is shown as unavailable rather than imitated.
- **Resolution — recover only when evidence permits (Events 8–10):** A deliberately biased return is rejected without moving the scientific state. A later credible fix passes screening and dwell consistency. Display recovery is smooth but visibly separate from the scientific update, and the final report uses only eligible scientific/reference evidence.

### 2.3 Evaluator takeaway

The demonstration is about controlled failure behaviour and evidence lineage, not a claim that GNSS can be replaced indefinitely. The strongest claim supported by the storyboard is that the intended system makes source mode, outage mechanism, uncertainty, subsystem availability, proposal status, update decisions, and metric provenance inspectable. Any performance claim must be backed by the run-specific evidence shown on screen and in the verified report.

## 3. Demonstration operating contract

### 3.1 Preferred mode

The safe, repeatable submission path is a verified `DETERMINISTIC_REPLAY`. It re-emits recorded I-01/I-02 inputs in preserved source order, time, and provenance through the same downstream contracts used by live acquisition. Only the source adapter differs. Replay is not described as a live drive.

The persistent application frame shows:

- `SOURCE: DETERMINISTIC_REPLAY` throughout the replay run;
- `DEMO` throughout the demonstration run;
- `SIMULATED OUTAGE` for the complete interval governed by the software mask;
- `© OpenStreetMap contributors` whenever any map content is visible.

The word `REPLAY` must remain unmistakably visible. Badges may wrap on compact screens but may not collapse into colour-only icons.

### 3.2 Preflight sequence

Before Event 1, the presenter moves through the WP-09.7 readiness states without treating them as demonstration events:

| Screen state | Presenter action | Required evidence or stop condition |
| --- | --- | --- |
| UI-00 `LAUNCH_CHECKS` | Open the app and allow local manifest/configuration checks. | Invalid or unknown configuration blocks the run. |
| UI-01 `PERMISSION_REQUIRED` | Grant only required Android permissions when applicable. | Denial leaves the application idle; no capability is inferred. |
| UI-02 `SOURCE_SELECTION` | Select verified `DETERMINISTIC_REPLAY`. | A corrupt or incomplete replay cannot be used as a normal demo. |
| UI-04 `REPLAY_READY` | Confirm scenario, manifest, configuration, and source labels. | Scenario/mask identity must be available before start. |
| UI-05 `INITIALIZING` | Start the run and wait for a valid anchor. | No moving scientific trace appears before valid I-07/I-08 output. |

If the app cannot satisfy a required preflight gate, the presenter stops and explains the typed failure. They do not switch to a prerecorded screen capture without labelling it as recorded presentation material.

### 3.3 Layer legend used in every frame

| Marker | Layer | Required presentation | Prohibited interpretation |
| --- | --- | --- | --- |
| `[S]` | Scientific estimate | Solid, explicitly labelled `SCIENTIFIC`; sourced from I-07 with paired I-08. | Must not be replaced by the display trace or a map-snapped point. |
| `[D]` | Display position | Dashed, explicitly labelled `DISPLAY (SMOOTHED)` when present. | Never fed into C-07 or used in endpoint, maximum-error, or RMSE metrics. |
| `[R]` | Reference/withheld baseline | Dotted, explicitly labelled `REFERENCE — WITHHELD`; optional and access-controlled. | During outage it is evaluation-only and never estimator input. |
| `[1..K]` | Map candidates | Individually numbered proposal geometry with status and evidence. | Never represented as scientific truth or forced nearest-road output. |

Route geometry and uncertainty bands receive their own labels and patterns. Colour is supplementary; label, marker, and line pattern carry the meaning.

### 3.4 Presenter truth vocabulary

- **Real:** generated by the actual code path during the run.
- **Recorded:** immutable source evidence collected earlier.
- **Replayed:** recorded evidence delivered again with preserved source ordering, timing, and provenance.
- **Simulated:** limited to the declared GNSS visibility mask and deliberately biased return fixture; always labelled.
- **Unavailable:** no eligible/evidenced output exists.
- **Experimental/Shadow:** an output may be observed but is not an accepted production influence or validated scientific result.

The presenter must not use “real-time,” “live,” “ground truth,” “AI-corrected,” “map-matched,” “accurate,” or “validated” unless the current run evidence and subsystem status support that exact statement.

### 3.5 Complete WP-09.7 screen-state crosswalk

The ten-event path uses the state subset identified below, but the storyboard inherits all UI-00 through UI-34 semantics. A fallback state is not an extra demonstration event and does not permit the presenter to skip or reorder an authoritative event.

| State ID | WP-09.7 state | Storyboard use |
| --- | --- | --- |
| UI-00 | `LAUNCH_CHECKS` | Mandatory preflight; blocks the demonstration on invalid configuration or capability. |
| UI-01 | `PERMISSION_REQUIRED` | Conditional preflight; denial remains idle. |
| UI-02 | `SOURCE_SELECTION` | Mandatory preflight selection of verified replay. |
| UI-03 | `LIVE_READY` | Live-only alternate path; not used in the default deterministic replay. |
| UI-04 | `REPLAY_READY` | Mandatory replay manifest and scenario confirmation. |
| UI-05 | `INITIALIZING` | Pre-Event-1 state; no scientific movement before valid output. |
| UI-06 | `GNSS_AIDED` | Event 1 and the post-acceptance mode reached after Event 9. |
| UI-07 | `QUALITY_DEGRADED` | Conditional health fallback before or during outage; reasons remain visible. |
| UI-08 | `SIMULATED_OUTAGE` | Event 2 and the declared I-14 mask interval. |
| UI-09 | `NATURAL_OUTAGE` | Alternate non-simulated path; never substituted for Event 2. |
| UI-10 | `BLACKOUT_DR_VALID` | Events 2–6 and, where policy applies, Events 7–8. |
| UI-11 | `OUTPUT_RATE_DEGRADED` | Event 3 fallback when measured cadence violates policy. |
| UI-12 | `SCIENTIFIC_FAULT` | Events 4/6 or any-run fail-closed state; blocks continuity claims. |
| UI-13 | `ALIGNMENT_UNAVAILABLE` | Persistent honest fallback while S3 lacks eligible evidence. |
| UI-14 | `ALIGNMENT_SLIP_SUSPECTED` | Conditional health state; disables alignment-dependent aids. |
| UI-15 | `MODEL_DISABLED` | Complete classical baseline state when S4 influence is off. |
| UI-16 | `MODEL_EXPERIMENTAL` | `SHADOW`/experimental S4 presentation without scientific influence claims. |
| UI-17 | `MODEL_FAILED` | Optional-subsystem failure; classical core may continue visibly. |
| UI-18 | `MAP_AVAILABLE` | Map-bearing event frames when the local map verifies and renders. |
| UI-19 | `MAP_UNAVAILABLE` | Honest map/renderer failure fallback with textual science retained. |
| UI-20 | `MATCHER_UNAVAILABLE` | Current-baseline Event 7 state unless runtime matching is evidenced. |
| UI-21 | `MAP_NO_CANDIDATE` | Event 7 eligible matcher result with no candidates; remains unmatched. |
| UI-22 | `MAP_AMBIGUOUS` | Event 7 eligible Top-K ambiguity/abstention state. |
| UI-23 | `MAP_CLEAR_EXPERIMENTAL` | Event 7 eligible experimental clear proposal; never scientific truth. |
| UI-24 | `RETURN_SCREENING` | Entry to Events 8 and 9. |
| UI-25 | `RETURN_REJECTED` | Event 8 terminal decision for the biased fixture. |
| UI-26 | `RETURN_DWELL` | Mandatory Event 9 consistency interval before acceptance. |
| UI-27 | `RETURN_ACCEPTED` | Event 9 accepted decision and scientific update evidence. |
| UI-28 | `DISPLAY_RECOVERY` | Event 10 cosmetic continuity with `[S]`/`[D]` separation. |
| UI-29 | `RECORDING_DEGRADED` | Conditional evidence warning; affected interval cannot support an undisclosed claim. |
| UI-30 | `RECORDING_INCOMPLETE` | Failure outcome; normal replay/complete-run claims are blocked. |
| UI-31 | `RUN_COMPLETE` | Event 10 controlled completion state. |
| UI-32 | `AFTER_RUN_REPORT` | Event 10 metrics, transitions, cadence, and provenance. |
| UI-33 | `REPLAY_PAUSED` | Rehearsal/operator control state; persistent labels and evidence remain visible. |
| UI-34 | `STALE_PRESENTATION` | Any-event fallback when I-16 age exceeds policy; historical state is not shown as current. |

## 4. Chronological storyboard overview

The event order is immutable for the submission narrative.

| Event | Authoritative behaviour | Primary UI state(s) | Narrative beat | Reality classification |
| ---: | --- | --- | --- | --- |
| 1 | Valid GNSS-aided start and anchor | UI-06 `GNSS_AIDED` | Establish a traceable scientific origin. | Real live fix or recorded/replayed fix. |
| 2 | Deliberate GNSS outage begins | UI-08 `SIMULATED_OUTAGE`; UI-10 `BLACKOUT_DR_VALID` | Declare the intervention before showing resilience. | Software-simulated. |
| 3 | Approximately 10 Hz output continues | UI-10; UI-11 only if degraded | Demonstrate measured continuity, not a hard-coded rate claim. | Real pipeline output on replayed inputs. |
| 4 | Inertial estimate continues | UI-10; UI-12 on scientific fault | Show genuine S2 propagation and state/covariance lineage. | Real S2 propagation. |
| 5 | Route turn occurs during outage | UI-10 | Make trace separation visually obvious at a meaningful manoeuvre. | Recorded/replayed or controlled live. |
| 6 | Uncertainty grows | UI-10; UI-12 on invalid covariance | Show decreasing certainty rather than false confidence. | Real computed covariance. |
| 7 | Top-K map candidates appear | UI-20 through UI-23 as capability permits | Explain bounded proposals, ambiguity, and abstention. | Real matcher output only once implemented; otherwise unavailable/experimental. |
| 8 | Deliberately biased returning fix rejected | UI-24 `RETURN_SCREENING`; UI-25 `RETURN_REJECTED` | Prove there is no first-fix privilege. | Simulated/fixture evidence. |
| 9 | Subsequent credible fix accepted | UI-24; UI-26 `RETURN_DWELL`; UI-27 `RETURN_ACCEPTED` | Show evidence-based return after consistency dwell. | Recorded or fixture evidence. |
| 10 | Display recovers smoothly; after-run comparison shown | UI-28; UI-31; UI-32 | Separate presentation continuity from scientific evaluation. | Display-derived plus scientific/reference report. |

## 5. Detailed storyboard and oral script

Runtime values below use angle brackets. A value that is unavailable must display `UNAVAILABLE`, `PENDING`, or `NOT COMPUTABLE` with a reason; it must never be replaced with a plausible number.

### Event 1 — Valid GNSS-aided start and anchor

| Storyboard field | Contract |
| --- | --- |
| Display layout and screen state | Map/Route is primary with Health visible in split or adjacent panel. Enter UI-06 `GNSS_AIDED` after UI-05 produces a valid anchor. Show `[S]` at the scientific anchor and configuration-derived uncertainty; do not hardcode a confidence percentage. |
| Visual badges and Health HUD | Persistent `SOURCE: DETERMINISTIC_REPLAY` and `DEMO`. No `SIMULATED OUTAGE` yet. Show GNSS `HEALTHY` only when I-13 says so; show Navigation `GNSS_AIDED`, actual Sensor/Alignment/Model/Map/Recording states, scientific age, and permanent `© OpenStreetMap contributors`. |
| Spoken narrative / judge explanation | “We begin from a valid GNSS-aided anchor. This is deterministic replay of recorded evidence, not a live drive. The provider, fix evidence ID, scientific state sequence, and uncertainty are visible so the starting condition is auditable.” |
| Telemetry and interface lineage | I-07 supplies scientific state sequence, epoch, origin, mode, and validity. I-08 supplies covariance tied to that exact state sequence. I-13 supplies independent health axes. I-16 supplies the read-only presentation snapshot. The underlying I-02 provider/fix evidence remains provenance-bearing. |
| Invariant checks | `[S]` is the only scientific marker. No display/reference/candidate layer is presented as the anchor. I-07 and I-08 sequences correspond. Map attribution remains visible. Alignment and model show their actual statuses, normally `UNAVAILABLE`/`UNINITIALIZED` and `DISABLED`/`SHADOW` at the current evidence level. |

**Operator cue:** Hold long enough for judges to read source mode, GNSS state, evidence ID, and uncertainty. Do not advance if the anchor or paired uncertainty is invalid.

### Event 2 — Deliberate GNSS outage begins

| Storyboard field | Contract |
| --- | --- |
| Display layout and screen state | Keep Map/Route primary and open the outage timeline/evidence strip. Transition through UI-08 `SIMULATED_OUTAGE` into UI-10 `BLACKOUT_DR_VALID` only if scientific propagation remains valid. If `[R]` is shown, mark it locked/withheld. |
| Visual badges and Health HUD | `SOURCE: DETERMINISTIC_REPLAY`, `DEMO`, and persistent `SIMULATED OUTAGE`. Show Navigation `BLACKOUT_DR`, GNSS `UNAVAILABLE`, scenario ID, mask ID, hidden-field list, and `© OpenStreetMap contributors`. |
| Spoken narrative / judge explanation | “The outage starts now. It is software-simulated and explicitly labelled. The mask hides GNSS from the estimator at declared epochs, while raw and optional reference evidence are retained separately for later evaluation.” |
| Telemetry and interface lineage | I-14 supplies event ID, start epoch, type, reason, mask ID, and hidden fields. I-07/I-08 continue only through valid scientific propagation. I-16 carries the mandatory labels and separate nullable reference position. |
| Invariant checks | The outage badge appears at the same declared interval as I-14. Withheld GNSS does not enter C-07. Raw evidence retention is not described as estimator use. A natural/quality outage is never labelled simulated, and network status is never used as GNSS health. |

**Operator cue:** Verbally say “software-simulated outage” before discussing continued navigation. Point to the badge and mask ID.

### Event 3 — Approximately 10 Hz output continues

| Storyboard field | Contract |
| --- | --- |
| Display layout and screen state | Remain in UI-10 with the scientific trace and output-evidence panel. If the measured cadence violates configured policy, also show UI-11 `OUTPUT_RATE_DEGRADED`; do not hide the degradation. |
| Visual badges and Health HUD | All three replay/demo/outage badges persist. Show observed output rate, interval distribution such as p50/p95 when computed, gap count, last I-07 sequence, and attribution. |
| Spoken narrative / judge explanation | “Scientific output continues during the outage. The displayed rate is measured from state epochs; it is not the screen refresh rate and not a hard-coded ten-hertz label. Any missed interval or reduced cadence remains visible.” |
| Telemetry and interface lineage | I-07 sequence and epoch provide scientific output intervals. I-08 remains paired per state. I-13 supplies sensor/navigation degradation reasons. I-16 staleness distinguishes current presentation from stale UI. |
| Invariant checks | The judge sees observed evidence rather than an asserted pass. UI refresh cadence is not substituted for core cadence. Gaps and thermal/resource degradation remain disclosed. No interpolation creates extra scientific samples. |

**Operator cue:** Quote the observed rate only after it appears. Use “approximately 10 Hz” only when the distribution supports it.

### Event 4 — Inertial scientific estimate continues

| Storyboard field | Contract |
| --- | --- |
| Display layout and screen state | In UI-10, show the solid `[S]` trace moving from the anchor with GNSS updates masked. Show current I-07 sequence/epoch/validity and I-08 linkage. Transition to UI-12 `SCIENTIFIC_FAULT` instead of continuing the trace if mandatory IMU or numeric validity fails. |
| Visual badges and Health HUD | Replay/demo/outage badges persist. Show Navigation `BLACKOUT_DR`, GNSS `UNAVAILABLE`, actual Sensor state, state age, and attribution. Alignment/model/map remain independent health axes. |
| Spoken narrative / judge explanation | “This solid line is the scientific S2 estimate propagated from accepted inertial input. It is not a held GNSS point, a display animation, or a snapped road position. If mandatory inertial input fails, the UI declares a fault instead of drawing plausible motion.” |
| Telemetry and interface lineage | I-07 is the canonical scientific state owned by C-07. I-08 is the tied covariance. I-13 provides Sensor and Navigation states/reasons. I-16 exposes the immutable scientific snapshot to UI. |
| Invariant checks | C-07 remains the only state owner. No S3 alignment estimate, S4 model output, map proposal, reference point, or display smoothing overwrites `[S]`. Invalid output is never shown as valid. |

**Operator cue:** Point to the `SCIENTIFIC` legend and sequence evidence, not merely the moving marker.

### Event 5 — Route turn occurs during outage

| Storyboard field | Contract |
| --- | --- |
| Display layout and screen state | Keep UI-10 and frame the route turn so `[S]`, optional `[D]`, optional `[R]`, and route geometry can be distinguished by labels and line patterns. `[R]` is absent if disclosure is disabled. |
| Visual badges and Health HUD | Replay/demo/outage badges and attribution persist. Health remains visible or one action away without replacing the legend. |
| Spoken narrative / judge explanation | “The turn makes divergence and continuity visually inspectable. The solid line is scientific `[S]`; the dashed line, if shown, is cosmetic display `[D]`; the dotted locked line is evaluation-only reference `[R]`. They are deliberately not interchangeable.” |
| Telemetry and interface lineage | I-07/I-08 drive `[S]` and uncertainty. I-16 carries separately marked `scientific_state`, nullable `display_position`, nullable `reference_position`, labels, and staleness. The route is presentation context governed by the verified map manifest. |
| Invariant checks | Geometry and legend remain distinguishable without colour. `[R]` does not enter inference during outage. `[D]` does not enter C-07. Route geometry does not imply field validation or map feedback. |

**Operator cue:** Trace each visible line from its legend to the turn. Explicitly say “display smoothing is cosmetic.”

### Event 6 — Computed uncertainty grows

| Storyboard field | Contract |
| --- | --- |
| Display layout and screen state | In UI-10, expand the uncertainty band/ellipse around `[S]` according to computed I-08 values. Show configured confidence text, major/minor axes when derived, and quality flags. Use UI-12 on nonfinite, dimension-invalid, or otherwise invalid scientific covariance. |
| Visual badges and Health HUD | Replay/demo/outage badges persist. Show `UNCERTAINTY GROWING` only when comparison of valid computed uncertainty supports it. Attribution remains visible. |
| Spoken narrative / judge explanation | “As external position updates remain unavailable, the computed covariance grows. We show that loss of certainty rather than keeping a falsely confident marker. The confidence level is configuration-derived, not hard-coded.” |
| Telemetry and interface lineage | I-08 provides the 15-state covariance, ordering ID, state sequence, and quality flags at the same epoch as I-07. I-16 carries the presentation uncertainty. |
| Invariant checks | The ellipse corresponds to the current I-07 sequence. Invalid covariance is surfaced rather than clipped into a reassuring shape. No fixed 95-percent claim appears unless the run configuration explicitly defines and evidences it. |

**Operator cue:** Point to both the growing geometry and numeric/configuration label; avoid claiming that larger uncertainty proves positional error by itself.

### Event 7 — Top-K map candidates appear

| Storyboard field | Contract |
| --- | --- |
| Display layout and screen state | Use Candidates alongside Map. Select the truthful state: UI-20 `MATCHER_UNAVAILABLE`, UI-21 `MAP_NO_CANDIDATE`, UI-22 `MAP_AMBIGUOUS`, or UI-23 `MAP_CLEAR_EXPERIMENTAL`. If eligible output exists, draw numbered `[1..K]` proposals without moving `[S]`. |
| Visual badges and Health HUD | Replay/demo/outage badges and attribution persist. Show map/matcher status, candidate score, entropy, margin, map version, and feedback `OFF` or `EXPERIMENTAL` when those values exist. |
| Spoken narrative / judge explanation | Preferred current-baseline wording: “Runtime Top-K matching is not yet evidenced, so it is shown as unavailable and no candidates are fabricated.” Eligible future wording: “These numbered roads are bounded hypotheses with ambiguity evidence; they do not overwrite the scientific estimate.” |
| Telemetry and interface lineage | I-11 supplies decision ID, I-07 state sequence, map version, 0..K candidates, entropy, margin, confidence, and status. I-16 carries a nullable map result and mandatory labels. |
| Invariant checks | No candidate telemetry appears without real I-11 output. Version/origin mismatch, no candidate, ambiguity, or abstention remains unmatched. `CLEAR` is not scientific truth. Map feedback status is explicit, and `[S]` remains independently labelled. |

**Operator cue:** Use the unavailable wording unless the exact demonstrated build has verified runtime matcher output. Never narrate a static mock overlay as live matching.

### Event 8 — Deliberately biased returning fix is rejected

| Storyboard field | Contract |
| --- | --- |
| Display layout and screen state | Transition from UI-24 `RETURN_SCREENING` to UI-25 `RETURN_REJECTED`. Place the rejected fix marker away from `[S]`, show “no scientific update,” and keep the outage/reacquisition timeline visible. |
| Visual badges and Health HUD | `SOURCE: DETERMINISTIC_REPLAY`, `DEMO`, and `SIMULATED OUTAGE` persist while the mask interval remains active. Show Navigation `REACQUIRING` or policy-defined DR state, Reacquisition `REJECTED`, fix ID, NIS, gate/configuration reference, typed reason, and attribution. |
| Spoken narrative / judge explanation | “This deliberately biased returning fix is fixture evidence. The system gives it no first-fix privilege: innovation screening produces this NIS result, the gate rejects it, its evidence ID is consumed once, and the scientific state does not jump.” |
| Telemetry and interface lineage | I-15 supplies event/fix ID, phase, NIS, gate, dwell count, accepted flag, reason, scientific jump, and display policy. I-07 sequence/update evidence confirms no accepted state update. I-14 identifies the still-active simulated interval where applicable. |
| Invariant checks | NIS is shown only after computation; before then it is `PENDING`, never zero. Rejection changes no C-07 state. Evidence is not offered twice. The biased return is explicitly simulated/fixture evidence. |

**Operator cue:** Pause on the rejection reason and unchanged `[S]`; this is the central integrity moment of the demo.

### Event 9 — Subsequent credible fix is accepted

| Storyboard field | Contract |
| --- | --- |
| Display layout and screen state | Show UI-24 screening, then UI-26 `RETURN_DWELL`, then UI-27 `RETURN_ACCEPTED`. Present dwell progress, consistency evidence, accepted fix ID, scientific update evidence, and separate `[S]`/`[D]` positions. |
| Visual badges and Health HUD | Replay and demo badges persist. `SIMULATED OUTAGE` disappears only at the configured mask end, not merely on visual proximity. Show Reacquisition phase, Navigation transition toward `GNSS_AIDED`, dwell `<count>/<required>`, consistency result, scientific jump, and attribution. |
| Spoken narrative / judge explanation | “A later credible fix is still not accepted immediately. It passes the innovation gate, remains consistent for the configured dwell, and only then produces an accepted scientific update. Acceptance follows evidence, not arrival order or closeness to the road.” |
| Telemetry and interface lineage | I-15 provides ordered SCREENING, DWELL, and ACCEPTED evidence, NIS/gate, dwell count, reason, and scientific jump. I-07 records the resulting state update and mode. I-08 provides its paired post-update covariance. |
| Invariant checks | No first-fix privilege. Dwell and consistency precede acceptance. Intermittent or inconsistent evidence resets/rejects according to policy. Acceptance is not inferred from `[D]`, `[R]`, route proximity, or map candidates. |

**Operator cue:** Do not skip the dwell frame. Contrast it explicitly with Event 8’s rejection.

### Event 10 — Smooth display recovery and after-run comparison

| Storyboard field | Contract |
| --- | --- |
| Display layout and screen state | Use UI-28 `DISPLAY_RECOVERY` to show `[S]` and `[D]` separately, then UI-31 `RUN_COMPLETE`, and UI-32 `AFTER_RUN_REPORT`. Show `[R]` only when eligible. Keep attribution visible while map content remains on screen. |
| Visual badges and Health HUD | `SOURCE: DETERMINISTIC_REPLAY` and `DEMO` persist through completion/report context. Show Recording `COMPLETE` or `INCOMPLETE`, run/config/build identities, endpoint error, maximum error, RMSE, transition summary, and measured output-rate distribution. Use full `© OpenStreetMap contributors`. |
| Spoken narrative / judge explanation | “The dashed display trace recovers smoothly for visual continuity, but it never changes C-07 and never enters these error metrics. The report compares the solid scientific estimate with eligible reference evidence and discloses transitions, output cadence, and recording completeness.” |
| Telemetry and interface lineage | I-15 supplies scientific jump and display policy. I-07/I-08 supply the scientific series. I-16 keeps scientific, display, and reference presentation separate. Report provenance includes run/config/build identities and eligible reference lineage; I-11 results are reported only if actually available. |
| Invariant checks | Endpoint, maximum, and RMSE exclude `[D]`. Missing, invalid, or time-incompatible `[R]` yields `NOT COMPUTABLE` plus reason. `INCOMPLETE` evidence blocks unsupported claims. Smooth display is not described as scientific accuracy. Attribution is unabbreviated. |

**Operator cue:** End on evidence scope, not a superlative. Invite the judge to inspect the timeline and run identity.

## 6. Presenter run card

This compact card supplements, but does not replace, the detailed storyboard.

| Beat | Show | Say | Verify before advancing |
| ---: | --- | --- | --- |
| 1 | `[S]` anchor; GNSS aided | “Recorded/replayed valid anchor with evidence identity.” | I-07/I-08 pair and provider/fix ID. |
| 2 | Outage badge and mask | “Software-simulated; GNSS hidden from estimator, retained separately.” | I-14 scenario/mask/hidden fields. |
| 3 | Rate evidence | “Measured core cadence, not UI refresh.” | Intervals and gaps are real values. |
| 4 | `[S]` propagation | “Scientific S2 state continues from inertial input.” | Validity and sensor health. |
| 5 | Turn with layer legend | “Scientific, display, and reference are separate.” | `[R]` evaluation-only; `[D]` cosmetic. |
| 6 | Growing uncertainty | “Computed covariance exposes declining certainty.” | Confidence is configured; I-08 valid. |
| 7 | Candidate state | “Unavailable today, or bounded proposals if evidenced.” | No fabricated I-11 rows. |
| 8 | Rejected biased return | “NIS gate rejects; no first-fix privilege or state jump.” | I-15 reason; no accepted C-07 update. |
| 9 | Screening, dwell, accept | “Credible return is accepted only after consistency.” | Ordered I-15 phases and I-07 update. |
| 10 | `[S]`/`[D]` and report | “Smoothing is cosmetic; metrics use scientific/reference data only.” | Metric eligibility, run identity, completeness. |

## 7. Rehearsal and failure protocol

### 7.1 Required rehearsal evidence

R5 and R6 record, for the exact demonstration build and scenario:

- application build/configuration identity;
- replay manifest, scenario, and mask identity;
- one screenshot or video timecode for each event;
- I-07 sequence and paired I-08 availability at Events 1, 4, 6, 9, and 10;
- I-14 evidence for Event 2;
- I-11 availability/status evidence for Event 7;
- ordered I-15 rejection/dwell/acceptance evidence for Events 8–9;
- output interval distribution and gaps for Event 3;
- recording completeness and metric eligibility for Event 10;
- confirmation that badges and full attribution persist in all map-bearing captures.

Passing repository CI or replay determinism alone is not drift evidence. Rehearsal artefacts must not include private routes, raw private coordinates, secrets, or prohibited data.

### 7.2 On-stage fallback language

| Condition | Required presenter response |
| --- | --- |
| Local map unavailable | “The local map renderer is unavailable in this build. The scientific state and health remain visible; no online map or cached substitute is being used.” |
| Runtime matcher unavailable | “Top-K runtime matching is not evidenced in this build, so the panel correctly shows unavailable and no candidates are fabricated.” |
| S3 alignment unavailable/uncertain | “Vehicle-frame alignment is unavailable or uncertain; alignment-dependent aids are disabled.” |
| S4 model disabled/shadow/failed | “The learned component is disabled or shadow-only. The classical scientific core continues, and no learned correction is claimed.” |
| Reference ineligible | “Reference evidence is unavailable or ineligible for this interval, so the metric is not computable.” |
| Scientific fault | “The scientific output is invalid and the UI has stopped presenting it as valid. We can inspect diagnostics, but we will not claim continuity.” |
| Recording incomplete | “This run is incomplete and cannot support the affected evidence claim.” |
| Replay control rejected | “The requested control was rejected; the existing run identity and evidence remain unchanged.” |

The presenter must not conceal a failure by changing labels, switching data sources mid-run, using a video as if it were interactive output, or quoting results from a different run.

## 8. Evaluator FAQ

### Is this a live drive?

No. The default safe demo is `DETERMINISTIC_REPLAY`, permanently labelled on screen. It replays recorded source evidence through the intended common downstream contracts. If a future demonstration uses `LIVE_DEVICE`, the source badge must change and the presenter must not reuse replay claims.

### Is the GNSS outage genuine?

The loss of estimator visibility is deliberately software-simulated through a declared I-14 scenario mask. It is not RF jamming and must never be called jamming. Raw GNSS and optional reference data may be retained separately for evaluation, but remain unavailable to the estimator throughout the masked interval.

### Does the reference line guide the estimate?

No. `[R]` is evaluation-only. It is optional, visibly locked/withheld during the outage, and never enters C-07. The scientific estimate `[S]` must remain identical whether the UI chooses to display `[R]` or hide it.

### Is the smooth line the navigation solution?

No. `[D]` is derived display continuity. `[S]` is the scientific estimate. Display smoothing never feeds C-07 and is excluded from endpoint error, maximum error, RMSE, and other scientific metrics.

### Is AI correcting the trajectory?

Not unless the exact run has an evidenced, eligible S4 proposal and accepted decision. At the current baseline S4 is incomplete; the UI must show `DISABLED`, `SHADOW`, `EXPERIMENTAL`, or `FAILED` as appropriate. No substitute correction or AI performance claim is permitted.

### Is phone-to-vehicle alignment solved?

Not at the current evidence baseline. S3 remains unevidenced/incomplete. The UI shows `UNAVAILABLE`, `UNINITIALIZED`, `UNCERTAIN`, or `SLIP_SUSPECTED` as applicable, and alignment-dependent aids stay disabled unless status is valid and evidenced.

### Are the road candidates map-matched truth?

No. `[1..K]` are bounded proposals from I-11 and may be absent, ambiguous, or rejected. They never overwrite `[S]`. Until runtime matching is implemented and evidenced, the truthful display is `TOP-K MATCHER UNAVAILABLE` with no synthetic candidates.

### Why reject the first returning GNSS fix?

Arrival after an outage does not make a fix credible. Event 8 intentionally supplies a biased fixture. C-09/C-07 use innovation evidence including NIS and configured gates; the rejected evidence is consumed once and produces no scientific update.

### Why wait after a good fix appears?

The reacquisition policy requires dwell and consistency rather than first-fix privilege. Event 9 shows SCREENING, DWELL, and ACCEPTED phases from I-15 before the accepted C-07 update.

### How are endpoint, maximum, and RMSE values produced?

They compare eligible scientific `[S]` states with eligible, time-compatible reference `[R]` evidence over a disclosed interval. The report includes units, sample count, provenance, and run/config/build identity. `[D]` is excluded. If the reference is missing or ineligible, the UI reports `NOT COMPUTABLE` with a reason.

### Does airplane mode affect the result?

The intended demonstration path uses verified local map data and local computation without runtime cloud inference or implicit downloads. Loss of network connectivity is not treated as GNSS health. If the local map fails, the UI retains textual scientific and health evidence and reports `MAP UNAVAILABLE`.

### Do passing tests prove navigation accuracy?

No. Tests and CI establish bounded software properties. Replay, architecture coverage, and passing smoke checks do not establish live drift performance, device generalization, or field validation. Those claims require separately reviewed run evidence.

## 9. Scientific-integrity checklist

Before recording, rehearsal, or judging, R5 and R6 confirm:

- [ ] Events 1 through 10 occur in exact authoritative order.
- [ ] `SOURCE: DETERMINISTIC_REPLAY` and `DEMO` persist for the full replay demo.
- [ ] `SIMULATED OUTAGE` persists for the exact I-14 mask interval.
- [ ] `© OpenStreetMap contributors` is full and visible whenever map content is displayed.
- [ ] `[S]`, `[D]`, `[R]`, and `[1..K]` are geometrically and textually distinct.
- [ ] Reference/withheld GNSS is unavailable to the estimator during the outage.
- [ ] Display smoothing is excluded from C-07 and scientific metrics.
- [ ] I-07 and I-08 are paired by state sequence/epoch.
- [ ] Event 3 reports measured output intervals and gaps, not UI refresh cadence.
- [ ] Event 6 uses configuration-derived confidence wording.
- [ ] Event 7 shows no candidate data unless eligible I-11 output exists.
- [ ] S3 and S4 statuses are evidence-bounded and never implied healthy.
- [ ] Event 8 shows NIS/gate/reason and no accepted state update.
- [ ] Event 9 shows screening and dwell consistency before acceptance.
- [ ] Event 10 excludes `[D]` from endpoint, maximum, and RMSE metrics.
- [ ] Missing/ineligible metrics display `NOT COMPUTABLE` with a reason.
- [ ] Recording completeness, run, configuration, and build identities are visible.
- [ ] No private route, raw private coordinate, secret, or prohibited artefact is exposed.

## 10. Acceptance-criteria traceability

| Requirement | Authority | Evidence in this document | Completion/verification gate |
| --- | --- | --- | --- |
| Define the SIH submission demo narrative. | Issue #112 | Sections 2–3 define the evaluator story, truth vocabulary, operating contract, and core takeaway. | R5/R6 narrative review and architecture-owner approval. |
| Define the storyboard. | Issue #112 | Sections 4–6 provide exact event order, detailed frame cards, spoken cues, evidence lineage, invariants, and run card. | One reviewed frame/timecode per event during rehearsal. |
| Preserve the authoritative ten-event sequence. | Demo Architecture; parent #16 | Sections 4–6 contain Events 1–10 in the same order and with the same behaviour classifications. | Sequence review; deterministic scenario mapping. |
| Bind the narrative to the UI contract. | WP-09.7 / Issue #78 | Sections 3–5 use UI-00–UI-32 as applicable, persistent badges, trace markers, Health HUD, and attribution; UI-33/UI-34 remain governed pause/stale fallbacks. | Review against WP-09.7 commit `3148da7`; later screenshot-state coverage. |
| Show source and simulation honestly. | I-14, I-16, I-17 | Sections 3.1, 5 Event 2, 7, and 8 require persistent replay/demo/outage labels and scenario evidence. | Badge screenshot matrix and I-14 interval comparison. |
| Separate scientific, display, reference, and candidate geometry. | I-07, I-08, I-11, I-16 | Section 3.3 and Events 5, 7, and 10 define `[S]`, `[D]`, `[R]`, and `[1..K]`. | Visual/accessibility review and data-lineage tests. |
| Exclude display smoothing from science and metrics. | Architecture Revision 3; parent #16 | Executive arc, Events 5 and 10, presenter card, FAQ, and checklist state the prohibition. | C-07 boundary review and report-input verification. |
| Keep withheld reference evaluation-only. | Architecture Revision 3; I-14/I-16 | Events 2 and 5 plus FAQ define locked, optional `[R]` and prohibit estimator access. | Scenario/data-lineage verification. |
| Bound claims for S3, S4, renderer, and matcher. | Demo truth table; development status | Sections 1, 5 Event 7, 7.2, and FAQ require `UNAVAILABLE`/`EXPERIMENTAL`/`SHADOW` and prohibit substitute telemetry. | Exact-build capability audit before rehearsal. |
| Demonstrate no first-fix privilege. | Events 8–9; I-15 | Event 8 documents NIS rejection/no update; Event 9 documents screening, dwell consistency, and acceptance. | Biased/good/intermittent fixture evidence and C-07 update audit. |
| Show honest after-run comparison. | Event 10; I-15/I-16 | Event 10 and FAQ define metric eligibility, provenance, completeness, and `[D]` exclusion. | Analyzer/report parity and missing-reference test. |
| Keep map attribution visible. | WP-09 acceptance / UI contract | Sections 3.1, all map-bearing cards, and checklist require the full string. | Portrait/landscape/pause/error/report screenshot review. |
| Provide judge-question handling. | Issue #112 submission scope | Section 8 supplies concise, evidence-bounded answers to expected technical questions. | R5/R6 oral rehearsal without unsupported claims. |
| Define failure-safe presentation. | Architecture failure model | Section 7 prevents substitutions and provides exact honest fallback language. | Capability-off/fault rehearsal. |

## 11. Ownership and handoff

### R5 — Android/frontend

- Ensures the implemented screen flow and capture plan match the UI state and badge contract.
- Verifies the trace legend, attribution, responsive presentation, and readable judge-facing evidence.
- Prevents display state or replay controls from mutating scientific state.
- Supplies exact-build screenshots/timecodes and identifies UI limitations.

### R6 — verification/evidence

- Verifies scenario, replay, run, configuration, build, and evidence identities.
- Confirms I-07/I-08 pairing; I-14 mask lineage; I-11 capability status; and I-15 rejection/dwell/acceptance sequence.
- Confirms after-run metric inputs, eligibility, interval, and completeness.
- Challenges claims that exceed the captured evidence and records `NOT COMPUTABLE`/`UNAVAILABLE` outcomes.

### Joint sign-off

R5 and R6 jointly confirm the ten-event order, spoken wording, visual evidence, privacy boundary, and failure fallback. Architecture/scientific claims require the designated reviewer and applicable CODEOWNER approval; self-review does not complete the gate.

## 12. Definition of done for WP-15.7

- The narrative follows Events 1–10 exactly and explains the evaluator arc.
- Every event specifies screen state, layout, badges/health, spoken cue, interface lineage, and invariant checks.
- UI-00 through UI-34 remain governed by direct traceability to WP-09.7, with the event-specific subset explicitly mapped.
- Replay, demo, simulated-outage, and map-attribution labels are persistent where required.
- `[S]`, `[D]`, `[R]`, and `[1..K]` remain separate in geometry, semantics, data lineage, and speech.
- Event 8 rejects the biased return using NIS/gate evidence without a C-07 update.
- Event 9 requires screening and dwell consistency before credible-fix acceptance.
- Event 10 excludes display smoothing from scientific metrics and discloses evidence eligibility.
- Unevidenced modules and missing metrics have honest fallback wording with no fabricated substitute telemetry.
- R5/R6 ownership, rehearsal evidence, evaluator FAQ, and acceptance traceability are documented.
- Repository verification passes after adding this Markdown file.
