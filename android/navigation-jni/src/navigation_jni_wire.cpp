#include "sih26168/navigation_jni.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cstring>
#include <limits>
#include <type_traits>
#include <unordered_set>

namespace sih26168::navigation::jni {
namespace {

class Writer {
public:
    explicit Writer(MessageKind kind) {
        integer(kWireMagic);
        integer(kWireVersion);
        integer(static_cast<std::uint16_t>(kind));
    }

    template <typename T>
    void integer(T value) requires std::is_integral_v<T> {
        using U = std::make_unsigned_t<T>;
        U bits = static_cast<U>(value);
        for (std::size_t index = 0; index < sizeof(T); ++index) {
            bytes_.push_back(static_cast<std::byte>((bits >> (index * 8U)) & 0xffU));
        }
    }

    void real(double value) { integer(std::bit_cast<std::uint64_t>(value)); }

    void string(const std::string& value) {
        integer(static_cast<std::uint32_t>(value.size()));
        for (const char character : value) bytes_.push_back(static_cast<std::byte>(character));
    }

    template <std::size_t N>
    void reals(const std::array<double, N>& values) {
        for (double value : values) real(value);
    }

    std::vector<std::byte> finish() { return std::move(bytes_); }

private:
    std::vector<std::byte> bytes_;
};

class Reader {
public:
    Reader(std::span<const std::byte> bytes, MessageKind expected) : bytes_(bytes) {
        if (bytes.empty() || bytes.size() > kMaximumMessageBytes) {
            status_ = BoundaryStatus::MalformedLength;
            return;
        }
        const auto magic = integer<std::uint32_t>();
        if (ok() && magic != kWireMagic) status_ = BoundaryStatus::InvalidMagic;
        const auto version = integer<std::uint16_t>();
        if (ok() && version != kWireVersion) status_ = BoundaryStatus::UnsupportedVersion;
        const auto kind = integer<std::uint16_t>();
        if (ok() && kind != static_cast<std::uint16_t>(expected)) {
            status_ = BoundaryStatus::UnexpectedMessageKind;
        }
    }

    template <typename T>
    T integer() requires std::is_integral_v<T> {
        if (!take(sizeof(T))) return T{};
        using U = std::make_unsigned_t<T>;
        U value = 0;
        for (std::size_t index = 0; index < sizeof(T); ++index) {
            value |= static_cast<U>(std::to_integer<unsigned char>(bytes_[offset_ + index]))
                << (index * 8U);
        }
        offset_ += sizeof(T);
        return static_cast<T>(value);
    }

    double real() { return std::bit_cast<double>(integer<std::uint64_t>()); }

    std::string string() {
        const std::uint32_t length = integer<std::uint32_t>();
        if (!ok() || length > kMaximumStringBytes || !take(length)) {
            if (ok()) status_ = BoundaryStatus::MalformedLength;
            return {};
        }
        std::string value(length, '\0');
        std::memcpy(value.data(), bytes_.data() + offset_, length);
        offset_ += length;
        return value;
    }

    template <std::size_t N>
    std::array<double, N> reals() {
        std::array<double, N> values{};
        for (double& value : values) value = real();
        return values;
    }

    bool ok() const { return status_ == BoundaryStatus::Ok; }
    BoundaryStatus status() const { return status_; }
    bool complete() const { return ok() && offset_ == bytes_.size(); }
    void fail(BoundaryStatus status) { if (ok()) status_ = status; }

private:
    bool take(std::size_t count) {
        if (!ok()) return false;
        if (count > bytes_.size() - std::min(offset_, bytes_.size())) {
            status_ = BoundaryStatus::MalformedLength;
            return false;
        }
        return true;
    }

    std::span<const std::byte> bytes_;
    std::size_t offset_{0};
    BoundaryStatus status_{BoundaryStatus::Ok};
};

template <typename E>
void writeEnum(Writer& writer, E value) {
    writer.integer(static_cast<std::int32_t>(value));
}

template <typename E>
E readEnum(Reader& reader, std::int32_t minimum, std::int32_t maximum) {
    const auto raw = reader.integer<std::int32_t>();
    if (reader.ok() && (raw < minimum || raw > maximum)) reader.fail(BoundaryStatus::InvalidEnum);
    return static_cast<E>(raw);
}

void writeHeaderlessState(Writer& writer, const StateSnapshot& value) {
    writer.integer(value.sequence.value);
    writer.integer(value.epoch_ns.nanoseconds);
    writeEnum(writer, value.navigation_frame);
    writeEnum(writer, value.body_frame);
    writer.reals(value.position_n_m);
    writer.reals(value.velocity_n_mps);
    writer.reals(value.q_n_b_wxyz);
    writer.reals(value.accel_bias_b_mps2);
    writer.reals(value.gyro_bias_b_radps);
    writer.string(value.origin_id.value);
    writeEnum(writer, value.mode);
    writeEnum(writer, value.validity);
}

StateSnapshot readHeaderlessState(Reader& reader) {
    StateSnapshot value;
    value.sequence.value = reader.integer<std::uint64_t>();
    value.epoch_ns.nanoseconds = reader.integer<std::int64_t>();
    value.navigation_frame = readEnum<NavigationFrame>(reader, 0, 0);
    value.body_frame = readEnum<BodyFrame>(reader, 0, 0);
    value.position_n_m = reader.reals<3>();
    value.velocity_n_mps = reader.reals<3>();
    value.q_n_b_wxyz = reader.reals<4>();
    value.accel_bias_b_mps2 = reader.reals<3>();
    value.gyro_bias_b_radps = reader.reals<3>();
    value.origin_id.value = reader.string();
    value.mode = readEnum<NavigationMode>(reader, 0, 5);
    value.validity = readEnum<StateValidity>(reader, 0, 1);
    return value;
}

void writeHeaderlessCovariance(Writer& writer, const CovarianceSnapshot& value) {
    writer.integer(value.state_sequence.value);
    writer.integer(value.epoch_ns.nanoseconds);
    writer.string(value.ordering_id);
    writer.reals(value.covariance_15x15);
    writer.integer(value.quality_flags);
}

CovarianceSnapshot readHeaderlessCovariance(Reader& reader) {
    CovarianceSnapshot value;
    value.state_sequence.value = reader.integer<std::uint64_t>();
    value.epoch_ns.nanoseconds = reader.integer<std::int64_t>();
    value.ordering_id = reader.string();
    value.covariance_15x15 = reader.reals<225>();
    value.quality_flags = reader.integer<std::uint32_t>();
    return value;
}

void writeSnapshots(Writer& writer, const SnapshotPair& value) {
    writeHeaderlessState(writer, value.state);
    writeHeaderlessCovariance(writer, value.covariance);
}

SnapshotPair readSnapshots(Reader& reader) {
    return {readHeaderlessState(reader), readHeaderlessCovariance(reader)};
}

BoundaryStatus finishStatus(const Reader& reader) {
    return reader.complete() ? BoundaryStatus::Ok
                             : (reader.ok() ? BoundaryStatus::MalformedLength : reader.status());
}

}  // namespace

std::vector<std::byte> encodeInitialState(const InitialState& value) {
    Writer writer(MessageKind::InitialState);
    writer.integer(value.state_sequence.value);
    writer.integer(value.source_timestamp.nanoseconds);
    writer.string(value.clock_id.value);
    writer.string(value.origin_id.value);
    writeEnum(writer, value.mode);
    writeEnum(writer, value.navigation_frame);
    writeEnum(writer, value.body_frame);
    writer.reals(value.position_n_m);
    writer.reals(value.velocity_n_mps);
    writer.reals(value.q_n_b_wxyz);
    writer.reals(value.accel_bias_b_mps2);
    writer.reals(value.gyro_bias_b_radps);
    writer.reals(value.covariance);
    return writer.finish();
}

DecodeResult<InitialState> decodeInitialState(std::span<const std::byte> bytes) {
    Reader reader(bytes, MessageKind::InitialState);
    InitialState value;
    value.state_sequence.value = reader.integer<std::uint64_t>();
    value.source_timestamp.nanoseconds = reader.integer<std::int64_t>();
    value.clock_id.value = reader.string();
    value.origin_id.value = reader.string();
    value.mode = readEnum<NavigationMode>(reader, 0, 5);
    value.navigation_frame = readEnum<NavigationFrame>(reader, 0, 0);
    value.body_frame = readEnum<BodyFrame>(reader, 0, 0);
    value.position_n_m = reader.reals<3>();
    value.velocity_n_mps = reader.reals<3>();
    value.q_n_b_wxyz = reader.reals<4>();
    value.accel_bias_b_mps2 = reader.reals<3>();
    value.gyro_bias_b_radps = reader.reals<3>();
    value.covariance = reader.reals<225>();
    return {finishStatus(reader), std::move(value)};
}

std::vector<std::byte> encodeImuBatch(const ImuBatch& value) {
    Writer writer(MessageKind::ImuBatch);
    writer.string(value.batch_id.value);
    writer.integer(value.first_seq.value);
    writer.integer(value.last_seq.value);
    writer.integer(value.gap_flags);
    writer.string(value.clock_id.value);
    writer.integer(static_cast<std::uint32_t>(value.samples.size()));
    for (const ImuSample& sample : value.samples) {
        writer.integer(sample.sequence.value);
        writer.string(sample.evidence_id.value);
        writer.integer(sample.source_timestamp.nanoseconds);
        writer.integer(sample.arrival_timestamp.nanoseconds);
        writeEnum(writer, sample.body_frame);
        writer.reals(sample.specific_force_b_mps2);
        writer.reals(sample.angular_rate_b_radps);
    }
    return writer.finish();
}

DecodeResult<ImuBatch> decodeImuBatch(std::span<const std::byte> bytes) {
    Reader reader(bytes, MessageKind::ImuBatch);
    ImuBatch value;
    value.batch_id.value = reader.string();
    value.first_seq.value = reader.integer<std::uint64_t>();
    value.last_seq.value = reader.integer<std::uint64_t>();
    value.gap_flags = reader.integer<std::uint32_t>();
    value.clock_id.value = reader.string();
    const auto count = reader.integer<std::uint32_t>();
    if (count > kMaximumSamples) reader.fail(BoundaryStatus::MalformedLength);
    if (reader.ok()) value.samples.reserve(count);
    for (std::uint32_t index = 0; reader.ok() && index < count; ++index) {
        ImuSample sample;
        sample.sequence.value = reader.integer<std::uint64_t>();
        sample.evidence_id.value = reader.string();
        sample.source_timestamp.nanoseconds = reader.integer<std::int64_t>();
        sample.arrival_timestamp.nanoseconds = reader.integer<std::int64_t>();
        sample.body_frame = readEnum<BodyFrame>(reader, 0, 0);
        sample.specific_force_b_mps2 = reader.reals<3>();
        sample.angular_rate_b_radps = reader.reals<3>();
        value.samples.push_back(std::move(sample));
    }
    return {finishStatus(reader), std::move(value)};
}

std::vector<std::byte> encodeMeasurement(const MeasurementInput& value) {
    Writer writer(MessageKind::Measurement);
    writer.integer(value.sequence.value);
    writer.string(value.measurement_id.value);
    writer.integer(value.state_epoch_ns.nanoseconds);
    writer.integer(value.arrival_timestamp.nanoseconds);
    writeEnum(writer, value.kind);
    writeEnum(writer, value.navigation_frame);
    writer.string(value.origin_id.value);
    writer.integer(static_cast<std::uint32_t>(value.provider_evidence_ids.size()));
    for (const EvidenceIdentifier& identifier : value.provider_evidence_ids) {
        writer.string(identifier.value);
    }
    writeEnum(writer, value.precheck.status);
    writer.string(value.precheck.reason_code);
    writer.reals(value.z);
    writer.reals(value.R);
    return writer.finish();
}

DecodeResult<MeasurementInput> decodeMeasurement(std::span<const std::byte> bytes) {
    Reader reader(bytes, MessageKind::Measurement);
    MeasurementInput value;
    value.sequence.value = reader.integer<std::uint64_t>();
    value.measurement_id.value = reader.string();
    value.state_epoch_ns.nanoseconds = reader.integer<std::int64_t>();
    value.arrival_timestamp.nanoseconds = reader.integer<std::int64_t>();
    value.kind = readEnum<MeasurementKind>(reader, 0, 2);
    value.navigation_frame = readEnum<NavigationFrame>(reader, 0, 0);
    value.origin_id.value = reader.string();
    const auto count = reader.integer<std::uint32_t>();
    if (count > kMaximumProviderEvidenceIds) reader.fail(BoundaryStatus::MalformedLength);
    if (reader.ok()) value.provider_evidence_ids.reserve(count);
    for (std::uint32_t index = 0; reader.ok() && index < count; ++index) {
        value.provider_evidence_ids.push_back({reader.string()});
    }
    value.precheck.status = readEnum<MeasurementPrecheckStatus>(reader, 0, 1);
    value.precheck.reason_code = reader.string();
    value.z = reader.reals<6>();
    value.R = reader.reals<36>();
    return {finishStatus(reader), std::move(value)};
}

std::vector<std::byte> encodePropagationResponse(const PropagationResponse& value) {
    Writer writer(MessageKind::PropagationResponse);
    writeEnum(writer, value.boundary_status);
    writeEnum(writer, value.result.status);
    writer.real(value.result.delta_time_seconds);
    writer.integer<std::uint8_t>(value.result.gap_detected ? 1U : 0U);
    writer.integer(value.result.state_sequence.value);
    writeSnapshots(writer, value.snapshots);
    return writer.finish();
}

DecodeResult<PropagationResponse> decodePropagationResponse(std::span<const std::byte> bytes) {
    Reader reader(bytes, MessageKind::PropagationResponse);
    PropagationResponse value;
    value.boundary_status = readEnum<BoundaryStatus>(reader, 0, 17);
    value.result.status = readEnum<PropagationStatus>(reader, 0, 17);
    value.result.delta_time_seconds = reader.real();
    const auto gap = reader.integer<std::uint8_t>();
    if (gap > 1U) reader.fail(BoundaryStatus::InvalidEnum);
    value.result.gap_detected = gap == 1U;
    value.result.state_sequence.value = reader.integer<std::uint64_t>();
    value.snapshots = readSnapshots(reader);
    return {finishStatus(reader), std::move(value)};
}

std::vector<std::byte> encodeMeasurementResponse(const MeasurementResponse& value) {
    Writer writer(MessageKind::MeasurementResponse);
    writeEnum(writer, value.boundary_status);
    writeEnum(writer, value.result.status);
    writer.integer(value.result.dimension);
    writer.real(value.result.normalized_innovation_squared);
    writer.integer(value.result.state_sequence.value);
    writeSnapshots(writer, value.snapshots);
    return writer.finish();
}

DecodeResult<MeasurementResponse> decodeMeasurementResponse(std::span<const std::byte> bytes) {
    Reader reader(bytes, MessageKind::MeasurementResponse);
    MeasurementResponse value;
    value.boundary_status = readEnum<BoundaryStatus>(reader, 0, 17);
    value.result.status = readEnum<MeasurementStatus>(reader, 0, 16);
    value.result.dimension = reader.integer<std::int32_t>();
    value.result.normalized_innovation_squared = reader.real();
    value.result.state_sequence.value = reader.integer<std::uint64_t>();
    value.snapshots = readSnapshots(reader);
    return {finishStatus(reader), std::move(value)};
}

std::vector<std::byte> encodeSnapshotResponse(const SnapshotResponse& value) {
    Writer writer(MessageKind::SnapshotResponse);
    writeEnum(writer, value.boundary_status);
    writeSnapshots(writer, value.snapshots);
    return writer.finish();
}

DecodeResult<SnapshotResponse> decodeSnapshotResponse(std::span<const std::byte> bytes) {
    Reader reader(bytes, MessageKind::SnapshotResponse);
    SnapshotResponse value;
    value.boundary_status = readEnum<BoundaryStatus>(reader, 0, 17);
    value.snapshots = readSnapshots(reader);
    return {finishStatus(reader), std::move(value)};
}

}  // namespace sih26168::navigation::jni
