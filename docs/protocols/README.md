# Controlled protocols

Protocols in this directory freeze an experiment before execution. A protocol
is not evidence that the experiment ran, passed, or established a scientific
claim.

## Registered protocols

- [`SIH26168-S3-v1`](SIH26168_S3_ALIGNMENT_AND_MOUNT_SLIP_PROTOCOL_v1.md):
  phone-to-vehicle alignment and mount-slip method-selection protocol. Its
  machine-readable twin is [`s3_alignment_protocol_v1.json`](s3_alignment_protocol_v1.json)
  and is validated against
  [`s3_alignment_protocol_v1.schema.json`](s3_alignment_protocol_v1.schema.json).

S3 remains unresolved until the later WP-06 implementation, controlled
execution, independent review, and result-publication issues complete. Editing
a frozen protocol after evidence collection starts requires a new protocol ID;
it must never silently change the gate applied to existing evidence.
