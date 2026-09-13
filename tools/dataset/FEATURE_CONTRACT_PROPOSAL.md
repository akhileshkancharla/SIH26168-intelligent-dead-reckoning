# Minimal causal feature contract proposal (WP-10.5)

Status: PROPOSED, pending owner review and source mapping evidence. This does
not activate `config/feature_firewall.json` or replace the accepted S0 audit.

Authority: Development Design Baseline section 5 (lines 83–85), I-03 ImuBatch
in `contracts/INTERFACE_SCHEMA_PLAN.md`, and I-19 input contract/normalization.
The public IO-VNBD paper, Table 5, describes smartphone channels:
https://pmc.ncbi.nlm.nih.gov/articles/PMC7907232/ . It does not prove column-to-axis
mapping, clock equivalence or approved schema IDs for the project's private copy.

| Proposed names | Trusted source | Unit / frame |
| --- | --- | --- |
| `imu.accel.x`, `.y`, `.z` | phone_accelerometer, corresponding x/y/z field | m/s^2, body |
| `imu.gyro.x`, `.y`, `.z` | phone_gyroscope, corresponding x/y/z field | rad/s, body |
| `imu.dt` | phone_imu_clock, dt | s, none |
| `imu.gap_mask`, `imu.valid_mask` | phone_imu_quality, matching field | dimensionless, none |

Names are proposed canonical identifiers. Binary masks are a proposed model
projection, not a change to I-03's bitfield contract. A reviewed extractor must
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

Every epoch must contain exactly the nine proposed channels; channel epochs must
increase strictly. Values must be finite, dt within I-03 bounds, masks binary,
and source/field/unit/frame exactly match the profile. Dependencies must include
all transform inputs, not just the output timestamp. A trusted extractor must
derive these records from pinned, reviewed mappings; caller-written metadata is
not proof of physical origin. Training code must call the composed gate before
consuming tensors. The repository currently has no production training extractor;
this API supplies validation, not end-to-end deployment or sensor authentication.

Before activation: ratify the names/masks; supply exact source-column, unit,
axis/frame and clock mappings for each approved schema; record evidence revision
and hash; freeze forbidden label identifiers; bind I-19 input/normalization to
the same contract. Add shipped-config exact-value tests and extractor parity
tests. Existing synthetic tests exercise source substitution, future/late data,
unknown GNSS features, malformed values, incomplete samples and inactive policy.
The old name-only API remains available for legacy callers and cannot establish
provenance or causality. The shipped template remains a hard stop.
