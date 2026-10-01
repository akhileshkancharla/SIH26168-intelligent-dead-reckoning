# Candidate phone-to-vehicle alignment estimator

This module implements the deterministic batch solvers predeclared as S3-M1
and conditional S3-M2 by `SIH26168-S3-v1`.

- M1 uses stationary raw-body specific-force evidence and qualified GNSS
  speed/course intervals. It first constrains gravity, then solves the remaining
  vehicle-yaw rotation from independently qualified dynamic acceleration.
- M2 requires contemporaneous raw-body I-03 evidence and uses paired I-07 body
  attitude and horizontal velocity snapshots as bounded alignment evidence. It
  is available for the protocol's conditional M2 execution only; this module
  does not choose between M1 and M2.
- Each I-07 observation used by M2 must pair one-to-one with a distinct,
  quality-eligible, non-stationary I-03 sample. Pairing selects the closest
  source epoch within `maximum_m2_pairing_skew_ns`; equal-skew candidates use
  the earlier I-03 sample. The fail-closed default is zero skew, so an explicit
  reviewed run configuration is required to permit nonzero timestamp skew.
  Only identities from completed pairs are reported as consumed evidence.
- Magnetometer input is absent from M1 and is neither required nor authoritative
  in M2.

Every input vector is copied for calculation and remains in its original frame.
The solvers reject malformed evidence and return no full rotation when motion
duration or excitation is insufficient. In particular, stationary gravity can
never produce a full candidate rotation.

## Deliberate boundary

The result is a **candidate solve outcome**, not an I-06 record. This module
does not assign `AlignmentStatusV1`, publish covariance, detect mount slip,
enable alignment-dependent aids, select a scientifically accepted method, or
modify C-07 navigation state.

## I-06 alignment posterior

The canonical Tier-C `contracts::AlignmentEstimate` POD is the bounded I-06
representation added by WP-06.3. It records the active body-to-vehicle
quaternion, a row-major 3x3 covariance in rad^2, explicit validity/failure
status, observability, nullable slip probability, and method/evidence/config
provenance. Its alignment-layer validator rejects
non-finite or non-canonical quaternions, non-symmetric or non-positive-semidefinite
covariance, out-of-range scalar values, and incomplete provenance.

`AlignmentEstimatePublisher` preserves the latest accepted posterior without
hidden overwrite. Sequence and epoch regressions are rejected. Any rejected
publication fails the dependent-aid gate closed until a newer valid posterior
is accepted. Only a structurally valid `VALID` posterior is eligible; the
`UNINITIALIZED`, `UNCERTAIN`, and `SLIP_SUSPECTED` states are never eligible.
Recovery from `SLIP_SUSPECTED` also requires evidence identity unseen in every
accepted slip or other non-`VALID` assessment since the incident began. Each
accepted non-`VALID` publication extends that recovery barrier; intermediate
state changes and repeated slips cannot recycle their own evidence to restore
eligibility.

This layer does not estimate covariance, infer scientific acceptance
thresholds, detect mount slip, choose between S3-M1 and S3-M2, or modify C-07
navigation state. Those remain with the later reviewed WP-06 work and S3
execution.
