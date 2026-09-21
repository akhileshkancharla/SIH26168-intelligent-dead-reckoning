# Minimal causal feature contract proposal (WP-10.5)

Status: ACTIVE structural contract, pending dataset-rights clearance before any
private experiment. This does not claim an S0 pass or permission to redistribute
the dataset.

Authority: Development Design Baseline section 5 (lines 83–85), I-03 ImuBatch
in `contracts/INTERFACE_SCHEMA_PLAN.md`, and I-19 input contract/normalization.
The accepted `SIH26168_IO_VNBD_Dataset_Feasibility_Audit_v1.1` and schema
register provide the reviewed source mapping. The audited upstream revision is
`118939602e3422d47b8ab0807b623751c3ac135b`.

| Proposed names | Trusted source | Unit / frame |
| --- | --- | --- |
| `imu.accel.x`, `.y`, `.z` | `S24_XYZ.accelerometer_x/y/z` through the reviewed phone adapter | m/s^2, body |
| `imu.gyro.x`, `.y`, `.z` | `S24_XYZ.gyroscope_x/y/z` through the reviewed phone adapter | rad/s, body |
| `imu.dt` | causal difference of validated `S24_XYZ.time_since_start` | s, none |
| `imu.gap_mask`, `imu.valid_mask` | adapter-derived from timestamp/sample validation evidence | dimensionless, none |

Names are frozen canonical identifiers. Binary masks are a model projection,
not a change to I-03's bitfield contract. A reviewed extractor must
define that projection and preserve gap/invalid evidence. This profile excludes
optional alignment/context/device-profile inputs and all GNSS inputs in all modes;
adding them requires a separately reviewed contract. Vehicle/VBOX/CAN/wheel
sources are never runtime sources, even when renamed to an allowed IMU name.

`enforce_feature_window` composes the ACTIVE name firewall with
`feature_provenance.validate_minimal_window`. Every timestamp must be a nonnegative
integer in the same declared clock domain. For every record:

```text
window_start <= dependency_start <= dependency_end <= sample_epoch
             <= available_at <= window_end
```

Every epoch must contain exactly the nine frozen channels; channel epochs must
increase strictly. Values must be finite, dt within I-03 bounds, masks binary,
and source/field/unit/frame exactly match the profile. Dependencies must include
all transform inputs, not just the output timestamp. A trusted extractor must
derive these records from pinned, reviewed mappings; caller-written metadata is
not proof of physical origin. Training code must call the composed gate before
consuming tensors. The repository currently has no production training extractor;
this API supplies validation, not end-to-end deployment or sensor authentication.

Every `V29_MAIN` interpreted field is frozen as a forbidden ID using
`V29_MAIN.<interpreted_field>`. This includes VBOX position/velocity/time fields
and all wheel, steering, yaw, engine, gear, pedal, brake and other CAN/ECU
fields. `V29_MAIN.velocity` is the conditional primary training label, but it
remains forbidden from runtime tensors, normalization, imputation,
preprocessing and post-processing. Tests assert all 29 IDs are rejected.

Sanitized evidence hashes:

- audit Markdown: `8F16194BA3E0BC0B521B6E240C98B93D4AC9CD0DEDA9A24455172F915C55A742`
- schema register CSV: `774964395A57CBDA87EBF0A60E32F63CF1DA6DBCF3C6E5D9C6B99D5EA0B2DF87`
- audit manifest JSON: `838B4CB4766DE1B0CE2E135432B5D765A2FB90B63448F7DEA629C2D4A31DCD1A`

The old name-only API remains available for legacy callers and cannot establish
provenance or causality. Rights clearance, a trusted extractor, I-19
normalization binding, and extractor parity remain experiment gates.
