# WP-07.1 GNSS fix precheck

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

The module deliberately does not implement WP-07.2 outage transitions,
WP-07.3 biased-fix or physical plausibility screening, WP-07.4 reacquisition
dwell, or the C-07 innovation gate.
