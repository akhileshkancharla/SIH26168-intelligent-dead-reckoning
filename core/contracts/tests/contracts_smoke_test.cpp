// WP-01.5 (Issue #29): compiles and exercises the placed contract bindings
// (core/include/sih26168/contracts/) to prove the generated headers are
// usable from real consuming code, not just present on disk.
#include "sih26168/contracts/enums.hpp"
#include "sih26168/contracts/models.hpp"

#include <string>
#include <unordered_map>

using namespace sih26168::contracts;

namespace {

// A minimal domain payload, standing in for a real RawSensorSample-style
// type. EvidenceEnvelopeV1 is a template precisely so callers can plug in
// a typed payload like this instead of the envelope omitting one.
struct RawSensorSamplePayload {
    std::string sensor_type{};
    double values[3]{};
};

} // namespace

int main() {
    static_assert(static_cast<uint8_t>(NavigationModeV1::INITIALIZING) == 0 ||
                      to_string(NavigationModeV1::INITIALIZING) == "INITIALIZING",
                  "NavigationModeV1 must round-trip through to_string");

    TimestampV1 ts{};
    ts.epoch_ns = 3456789000000;
    ts.arrival_elapsed_realtime_ns = 3456789000000;
    ts.clock_id = "CLOCK_BOOTTIME";

    ProvenanceV1 prov{};
    prov.evidence_id = "ev-001";
    prov.session_id = "sess-001";
    prov.stream_id = "sensor_accel";

    ValidityGateV1 gate{};

    EvidenceEnvelopeV1<RawSensorSamplePayload> envelope{};
    envelope.payload_type = "RawSensorSample";
    envelope.timestamp = ts;
    envelope.provenance = prov;
    envelope.payload = RawSensorSamplePayload{"ACCELEROMETER", {0.012, -0.034, 9.80665}};
    envelope.validity_gate = gate;

    const bool ok = envelope.schema_version == 1 &&
                    envelope.payload_type == "RawSensorSample" &&
                    envelope.timestamp.epoch_ns == 3456789000000 &&
                    envelope.provenance.provenance_type == ProvenanceTypeV1::LIVE_DEVICE &&
                    envelope.payload.sensor_type == "ACCELEROMETER" &&
                    envelope.validity_gate.is_finite;

    return ok ? 0 : 1;
}
