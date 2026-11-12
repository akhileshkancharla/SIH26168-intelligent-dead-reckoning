# GNSS host components

## WP-07.1 fix precheck

`FixPrecheck` screens I-02 candidate fixes before C-09 constructs an I-12
measurement or asks C-07 to consider an update. The source fix, including its
provider, clocks, field mask and mock flag, remains evidence. A decision of
`Eligible` means only that this precheck passed; it is not a GNSS integrity
decision, accepted core update, recovery event or navigation mode transition.

The caller supplies the active session, boot and monotonic clock identities,
source kind, provider and maximum source age. A maximum age is required because
Architecture Revision 3 leaves the operational GNSS freshness threshold
provisional; this work package does not choose one. Times are boot-scoped
monotonic nanoseconds. Wall/UTC times are not compared. Replay must retain its
source identity and use the same precheck under a replay policy.
Only the defined `Live` and `Replay` source kinds are valid. An unknown policy
kind rejects as `InvalidPolicy`; an unknown fix kind rejects as
`InvalidSourceKind` even if its malformed numeric value matches the policy.

Every nonempty evidence ID is consumed on first presentation, even if the fix
fails schema, provenance, timing or numerical checks. An eligible fix advances
the last accepted sequence and source epoch for its provider. A rejected fix
cannot poison that ordering baseline. The source evidence still belongs in the
append-only writer; this library performs no I/O and has no navigation state.

The I-02 JSON schema currently omits session, boot, clock and sequence keys
despite the interface plan requiring stream identity and ordered delivery.
They must be supplied from the enclosing provenance/timestamp context at the
adapter boundary; a caller must not guess them from wall time or another boot.
This library does not change the versioned I-02 schema or generated bindings.

The precheck deliberately does not implement WP-07.2 outage transitions,
WP-07.3 biased-fix or physical plausibility screening, WP-07.4 reacquisition
dwell, or the C-07 innovation gate.

## WP-07.2 outage-state tracker

`OutageStateTracker` owns only C-09's advisory GNSS-availability and navigation-
mode transitions. It starts at `UNAVAILABLE` / `INITIALIZING`; it enters
`HEALTHY` / `GNSS_AIDED` only when its caller attests both a unique, accepted
C-07 GNSS update and independent C-09 `HEALTHY` screening. A precheck-eligible
fix is **not** an accepted or healthy update. The tracker validates the
attestation values, but cannot itself prove an upstream C-07 decision.

The frozen run policy supplies nonzero, strictly ordered degradation and
unavailability durations. A monotonic tick first enters `DEGRADED`, then
`UNAVAILABLE` / `BLACKOUT_DR`; a late tick records the exact threshold epoch
as the outage onset, not the time the tick happened. An explicit natural,
quality, or software-simulated declaration can enter blackout immediately.
If an input arrives after a missed unavailability deadline, the timeout is
applied first, but the late input is rejected; a caller must not mistake that
state change for accepted aid or a valid declaration.
The simulated path requires a nonempty mask ID from an independently validated
and frozen C-12 scenario; this module never masks or rewrites raw GNSS data.

All calls carry matching session, boot and monotonic-clock identity. A returning
candidate must carry a successful WP-07.1 precheck decision and only enters
`CANDIDATE_RETURN` / `REACQUIRING`. Rejection returns to the *same* open outage.
Neither a first candidate nor a forged accepted-aid call can restore aiding
from blackout or reacquiring. WP-07.4 must implement the later validated
recovery gate; WP-07.3 must implement biased-fix/physical-plausibility checks.
`FAULT` is terminal. The tracker cannot mutate C-07 state or covariance.

The snapshot exposes the open outage onset, type, reason and optional mask ID
for later I-14 writer integration, but it is not itself a finalized I-14
manifest or a complete session log. Native tests are registered as
`gnss-outage-native`; no field performance or integrated Android path is
claimed.

Within a valid clock context and permitted mode, the first nonempty aid or
candidate evidence ID is consumed before its attestations are checked. A
rejected ID cannot be re-presented with upgraded C-07/C-09 or precheck claims;
the aid and candidate paths share one evidence ledger. Invalid clock contexts,
terminal faults, and disallowed mode transitions fail before ledger mutation.

## WP-07.3 fix rejection screen

`FixRejectionScreen` composes the WP-07.1 evidence-once precheck with a bounded
physical displacement check. Stale, duplicate, malformed and wrong-provenance
fixes are rejected before canonical I-12 construction. A biased jump exceeding
the distance allowed by elapsed source time, the frozen run's maximum ground
speed, and the two reported horizontal-accuracy radii is also rejected before
C-07. Fixes with reported uncertainty beyond the run's accuracy ceiling are
rejected before that comparison. No empirical speed or accuracy threshold is
chosen here: callers must provide finite positive values from a separately
approved frozen policy. A valid first
fix cannot establish a displacement baseline until C-07 actually accepts its
canonical update. Rejected fixes never become that baseline.

The precheck's evidence ledger advances on first presentation, including
rejected fixes. Calls are serial: the caller must supply the matching C-07
measurement result before another candidate can enter. An actual C-07
`RejectedInnovationGate` result is recorded as an innovation rejection; this
screen does not compute NIS, mutate C-07, or infer a statistically biased fix
from source coordinates alone. It cannot authenticate a caller-forged C-07
result, and the operational speed bound remains unapproved until a run policy
is frozen. Displacement screening cannot detect a slowly drifting bias or
replace C-07's innovation gate. WP-07.4 still owns reacquisition dwell and
restoration of GNSS aiding; this work does not promote candidate return.

Synthetic native coverage is registered as `gnss-rejection-native`. No live
Android integration, device accuracy, or field safety is claimed.

## WP-07.4 reacquisition gate

`ReacquisitionGate` runs on the serial native executor with the WP-07.2 outage
tracker, WP-07.3 rejection screen and C-07 navigation core. Every returning
source fix is presented to WP-07.1/07.3 exactly once. The first eligible fix
enters `REACQUIRING`, but is only screened by C-07's **non-mutating** innovation
gate. A screened fix that has not finished the dwell is explicitly withheld;
it does not change C-07 state or covariance or become the WP-07.3 displacement
baseline. C-07 consumes each canonical measurement ID on first presentation,
including screened and rejected candidates; C-09 has no shadow canonical ledger.
C-09 also requires an independently supplied `HEALTHY` quality screening;
neither source freshness nor a small NIS alone is sufficient. Later fixes must
independently pass the same C-07 innovation gate,
arrive within the configured inter-fix gap, and satisfy both the configured
minimum count (at least two) and positive elapsed dwell. Only the final fix is
submitted directly to C-07's authoritative atomic `update()` without a prior
screen of that same ID; recovery occurs only after that update actually succeeds.
An inconsistent, biased, duplicated or intermittent
return falls back to the same open blackout without a first-fix correction.

The count, minimum/maximum dwell and gap are required frozen-run policy inputs;
this component does not claim an empirically approved value for OD-09. The
native result exposes source identity, C-07 NIS, typed screening/update status,
dwell count and scientific update distance for later I-15 evidence assembly.
It does not serialize a complete I-15 record, implement C-11 display smoothing,
authenticate a caller's `HEALTHY` attestation or canonical source-to-measurement
adaptation, or wire the
standalone S1 logger into the Android app. The final C-07 update is still the
single scientific state owner. Host synthetic tests are registered as
`gnss-reacquisition-native`; no device or field-accuracy result is claimed.
