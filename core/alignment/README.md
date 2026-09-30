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
modify C-07 navigation state. Those responsibilities remain with later WP-06
issues and the reviewed S3 execution.
