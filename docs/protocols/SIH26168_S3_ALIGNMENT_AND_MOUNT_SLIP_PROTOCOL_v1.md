# S3 phone-to-vehicle alignment and mount-slip protocol v1

**Protocol ID:** `SIH26168-S3-v1`

**Status:** `FROZEN_BEFORE_EXECUTION`

**Architecture:** Revision 3

**Frozen base:** `11a8fb7519e4095f5235cda9589de9ce8b536df0`

**Tracking:** Issue #55; open decision OD-04

This document freezes the S3 experiment before any outcome is inspected. Its
normative machine-readable twin is
[`s3_alignment_protocol_v1.json`](s3_alignment_protocol_v1.json), validated by
[`s3_alignment_protocol_v1.schema.json`](s3_alignment_protocol_v1.schema.json).
If prose and JSON disagree, execution must stop and a reviewed protocol revision
must resolve the disagreement before collection.

This freeze is not execution evidence. It does not pass S3, close OD-04, select
a method, validate a live-car feature, or justify an alignment-dependent aid.
Any later claim is limited to the named devices, mounts, vehicle, software and
scenarios in the reviewed evidence package.

## 1. Safety and architecture invariants

1. C-05 owns I-06 outside S2. C-07 remains the only owner of navigation state,
   operational biases, covariance and evidence acceptance.
2. Raw I-03 IMU axes and all source clocks, arrival clocks, sequence numbers and
   evidence identifiers remain unchanged. Alignment is never applied by
   rewriting propagation samples.
3. Only an evidenced `VALID` I-06 status may enable alignment-dependent learned
   or kinematic aids. `UNINITIALIZED`, `UNCERTAIN` and `SLIP_SUSPECTED` disable
   every such aid; independent S2 propagation continues.
4. Dependent aids are disabled atomically before, or in the same decision as,
   publication of `SLIP_SUSPECTED`. A pre-slip estimate is never reused as
   `VALID` after a slip.
5. Stationary gravity may constrain roll and pitch but cannot establish vehicle
   yaw. Insufficient excitation must not be converted into a confident yaw.
6. The reference system and qualified GNSS or vehicle observations are bounded
   alignment or evaluation evidence. They are not hidden navigation truth.

All vehicle work requires institutional permission, a safe route and a safety
supervisor. The driver must never operate the phone or mount. A passenger or
test operator performs any required action. Controlled slip should be induced
while stationary; supervised low-speed execution is allowed only when the
approved run sheet explains why stationary execution cannot test the candidate.
Abort immediately for unsafe traffic, loose equipment, supervisor instruction,
reference failure or loss of a mandatory evidence stream. A safety abort is a
recorded outcome, never silently discarded.

## 2. Frozen hypotheses and candidates

| ID | Predeclared hypothesis or method |
|---|---|
| S3-H0 | Stationary gravity cannot make full vehicle alignment observable. Publishing `VALID` from stationary-only evidence falsifies this control. |
| S3-H1 | Gravity plus qualified straight and turning motion can make a bounded body-to-vehicle rotation observable. |
| S3-H2 | I-06 covariance and status conservatively expose insufficient excitation or disagreement. |
| S3-H3 | A controlled mount rotation of at least 15 degrees is detected and disables dependent aids within the frozen latency. |
| S3-H4 | The selected method remains safe with magnetometer evidence absent. |
| S3-M0 | Negative control: stationary gravity only. It is never selection-eligible and magnetometer input is forbidden. |
| S3-M1 | Candidate: raw-body I-03, qualified I-02 GNSS speed/course and I-04 quality state. Magnetometer input is forbidden. |
| S3-M2 | Candidate: raw-body I-03, paired I-07 velocity/attitude, I-04 quality state and optional non-authoritative raw magnetometer evidence. |

Candidates are evaluated in the fixed rank order M1, then M2. M1 completes
before M2 begins. M2 is executed only if M1 fails, but every conditional M2 run
assignment and seed is frozen before M1 collection starts. The first candidate
passing every invariant, mandatory scenario and threshold is selected. If
neither passes, the result is **no method selected** and S3 remains unresolved.
M0 can only demonstrate that the implementation fails closed.

## 3. Design and qualification rules

Before collection, the reviewed run sheet names at least two devices, three
mount orientations per device, one vehicle, candidate, scenario, repetition and
seeded run order. Every scenario minimum in section 4 applies separately to
each evaluated candidate and each named device. Runs are balanced as evenly as
possible across the device's three or more mounts, with at least one run on
every mount. S3-S01 has at least three runs on every mount. Each reference
body-to-vehicle transform is independently measured with at most 1 degree
stated rotation uncertainty. The operator who records the reference must not
edit candidate output or outcome labels.

A motion segment is eligible only when it lasts at least 10 seconds, speed is at
least 3.0 m/s, reported GNSS bearing accuracy is at most 5 degrees and reported
speed accuracy is at most 0.5 m/s. A turn additionally changes heading by at
least 30 degrees. `VALID` counts only after it remains continuous for 2 seconds.
Each no-slip observation lasts at least 60 seconds.

These values are feasibility gates selected before data collection, not claims
of universal field performance. A failed gate is reported for its device,
mount, scenario and candidate. Results must not be pooled across those groups to
hide a failure.

## 4. Mandatory scenario matrix

| ID | Minimum runs | Required execution |
|---|---:|---|
| S3-S01 | 9 | Stationary-only negative control across three documented mounts with independent transforms. |
| S3-S02 | 6 | Qualified straight motion in at least two travel directions. |
| S3-S03 | 6 | Qualified left and right turns with no outcome-based trimming. |
| S3-S04 | 6 | Magnetometer withheld; all ordinary accuracy and safety gates still apply. |
| S3-S05 | 6 | Secure mount, normal road vibration and at least 60 seconds of no-slip observation per run. |
| S3-S06 | 12 | Predeclared slip epoch; rotations of at least 15 degrees over yaw and roll or pitch axes; safe stationary or supervised low-speed execution. |
| S3-S07 | 6 | Post-slip re-excitation; a recovered estimate gets a new evidence identity and cannot inherit pre-slip validity. |
| S3-S08 | 1 | One immutable verified session replayed twice from unchanged input, producing byte-identical decisions and I-06 records. |

For every run: verify the protocol and software hashes; verify clocks and device
identity; record capabilities; acquire the independent reference; execute only
the preassigned row; preserve all raw and derived evidence; compute metrics
without manual repair; and record pass, fail, abort or allowed exclusion. Run
identity and scenario may not be changed after output is observed.

## 5. Metric definitions

Quaternions are normalized before comparison and use the shortest rotation. For
reference quaternion \(q_r\) and estimated quaternion \(q_e\), the geodesic
rotation error is

\[
e_R = 2\,\operatorname{acos}(\operatorname{clamp}(|w(q_r q_e^{-1})|,0,1)).
\]

Roll and pitch errors are absolute wrapped component differences. Yaw error is
the absolute principal-angle difference in \([-180,180)\) degrees. Non-finite or
non-normalizable values are invalid I-06 records, not missing samples.

For a three-component small-angle error \(e\) and declared I-06 covariance
\(P\), covariance coverage is true when
\(e^T P^{-1}e \le 7.814727903\), the predeclared 95 percent chi-square boundary
for three degrees of freedom. A non-finite, non-symmetric, non-positive-definite
or singular covariance fails coverage and increments the invalid-record count.

Nearest-rank percentile means sorting \(N\) eligible observations and selecting
the one-based element \(\lceil pN\rceil\). Time-to-valid begins at the first
eligible excitation sample and ends at the first 2-second sustained `VALID`
interval. Slip latency begins at the predeclared physical slip epoch and ends at
the first `SLIP_SUSPECTED` record. A missed slip has infinite latency and fails
the detection gate.

## 6. Frozen acceptance gates

Every applicable candidate/device/mount/scenario group must pass. Aggregates are
also reported per candidate/device/scenario, but they cannot rescue a failed
mount stratum:

| Gate | Required value |
|---|---:|
| Median geodesic rotation error | at most 5.0 deg |
| P95 geodesic rotation error | at most 10.0 deg |
| P95 roll/pitch error | at most 5.0 deg |
| P95 yaw error | at most 10.0 deg |
| P95 sustained time-to-valid | at most 15.0 s |
| 95% covariance coverage | at least 0.90 |
| Invalid/non-conformant I-06 records | 0 |
| Stationary false-`VALID` records | 0 |
| Eligible controlled-slip detection rate | 1.00 |
| P95 controlled-slip detection latency | at most 1.0 s |
| `SLIP_SUSPECTED` transitions in no-slip controls | 0 |
| Dependent-aid unsafe enables | 0 |
| Unchanged-input replay byte mismatches | 0 |

Accuracy and convergence gates apply where the scenario provides the necessary
excitation and reference. Safety, contract, status, exclusion and replay gates
are unconditional. Absent magnetometer evidence does not relax any gate.

## 7. Evidence, exclusions and decision record

The evidence package contains the approved run sheet; an I-18 manifest with
immutable hashes and completeness; raw I-01/I-02/I-03/I-04 and paired I-07
records; reference transforms and uncertainty; device capabilities; protocol,
commit, configuration and analyzer hashes; every I-06 record; every status and
dependent-aid decision; exclusions; per-run metrics; and group aggregates.
Private raw recordings remain in the controlled evidence store and are not
committed publicly.

Allowed exclusions are a predeclared safety abort, cryptographic integrity
failure, a reference failure documented before outcome inspection, or mandatory
stream loss that marks the session incomplete. Large errors, missed slips, false
alarms and inconvenient scenarios are never exclusion reasons. Missing evidence
must not be interpolated or inferred.

The reviewed result records one of: M1 selected, M2 selected, or no method
selected. Selection still does not close OD-04 by itself: WP-06 implementation,
controlled execution, independent review and result publication must complete.
Issues #56 through #60 own those downstream steps.

## 8. Change control and WP-06.1 completion

Before the first run, this protocol requires a signed, reviewed commit. After
the first run starts, any substantive edit requires a new protocol ID and a
separate evidence set; old evidence is never regraded with a new threshold.

WP-06.1 is complete only when the prose, JSON, schema and contract tests agree,
repository policy checks pass, generated architecture evidence is reproducible,
and reviewers approve the freeze. No experiment is executed in WP-06.1, so S3
and OD-04 remain explicitly unresolved.
