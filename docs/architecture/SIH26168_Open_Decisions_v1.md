# SIH26168 Open Decisions v1

| ID | Decision needed | Current position | Evidence/exit criterion | Blocks |
| --- | --- | --- | --- | --- |
| OD-01 | Official drift formula/aggregation | Report endpoint, maximum, RMSE/percentiles and distance-normalized values | Organizer protocol/clarification | Compliance claim only |
| OD-02 | Official 10 Hz and transition-latency boundary | Target scientific output ~10 Hz; profile all boundaries | Organizer definition + integrated traces | Performance claim |
| OD-03 | Supported Android device/API matrix | min 28/target 36 bootstrap only | Completed named S1 three-tier protocol | Device support claim |
| OD-04 | S3 alignment/slip method | Interface frozen; algorithm unknown | Controlled orientation/slip spike | Live car constraints/demo claim |
| OD-05 | Calibration/noise profiles | Conservative priors | Physical device/stationary/thermal data | Tuned performance |
| OD-06 | Learned model architecture/window/heads | Forward-speed proposal candidate; disabled baseline | Private leakage-safe baseline/ablation and S4 | Model-enabled influence |
| OD-07 | Model runtime/quantization | ONNX Runtime Mobile candidate | Android op/size/latency/golden parity | Model packaging |
| OD-08 | IO-VNBD public metrics/weights/redistribution | Private SIH use only; release conditional | Written scope-specific permission/licence | Public weights/data-derived release |
| OD-09 | Runtime reacquisition thresholds | Policy shape frozen; numbers provisional | Predeclared biased/good/intermittent fixtures + device data | Release gate |
| OD-10 | Matcher K/score/confidence/map-feedback thresholds | Top-K/abstain frozen; numbers provisional; feedback off | S6 characterization then frozen test | Map influence |
| OD-11 | Android PMTiles/MapLibre viability/assets | Provisional primary | Airplane-mode named-device footprint/start/memory/licence gates | Map UI freeze |
| OD-12 | Final MGIT route | None selected; both candidates field-pending | Permission, legal access, safety, current drivability/stopping inspection | Live field route only |
| OD-13 | External IMU packet/transport and ~200 Hz meaning | Canonical adapter; transport-neutral | Organizer format and profiling | Final edge conformance claim |
| OD-14 | Ground-truth/reference system | Withheld GNSS is demo reference only unless qualified | Documented reference accuracy/frame/time/lever arms | Drift/lane claim |
| OD-15 | Recording retention/access/deletion | App-private + explicit export | Team privacy policy/consent | Field collection |
| OD-16 | Two-wheeler scope | No transfer from car evidence | Separate data/protocol and official need | Two-wheeler claim |
| OD-17 | Exact dependency/tool patch pins | Families selected | Bootstrap lock update with compatibility CI | First build, not architecture |
| OD-18 | I-20 `file_group_ids` contract amendment | WP-10.3's grouping tooling implements a `file_group_ids` field (full identifier -> group_id membership) that WP-10.1's schema currently declares required; `INTERFACE_SCHEMA_PLAN.md#I-20`'s Required Fields list and explicit "Optional Fields: None" have not been updated to include it, so this is not yet an owner-ratified contract amendment | Owner decision: either ratify by updating I-20's Required Fields list in `INTERFACE_SCHEMA_PLAN.md` (an ADR is not required for an additive field to an already-Tier-A schema, but the interface plan itself is authoritative and must list it), or direct its removal from `dataset_manifest_v1.schema.json` | PR #142 (WP-10.1) and #144 (WP-10.3) final approval |

No open item above blocks WP-00 repository bootstrap. OD-04, OD-09, OD-10/11 and OD-12 are the most immediate demo-path gates; OD-06/07 do not block the model-disabled demonstration. OD-18 blocks WP-10.1/10.3 final approval only.
