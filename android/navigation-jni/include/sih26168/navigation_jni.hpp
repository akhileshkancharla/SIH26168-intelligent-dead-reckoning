#pragma once

#include "sih26168/navigation_core.hpp"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <span>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace sih26168::navigation::jni {

constexpr std::uint32_t kWireMagic = 0x494E4A53U;  // "SJNI" little-endian.
constexpr std::uint16_t kWireVersion = 2;
constexpr std::size_t kMaximumMessageBytes = 1024U * 1024U;
constexpr std::size_t kMaximumStringBytes = 4096U;
constexpr std::size_t kMaximumSamples = 1024U;
constexpr std::size_t kMaximumProviderEvidenceIds = 64U;

enum class MessageKind : std::uint16_t {
    InitialState = 1,
    ImuBatch = 2,
    Measurement = 3,
    PropagationResponse = 4,
    MeasurementResponse = 5,
    SnapshotResponse = 6,
};

enum class BoundaryStatus : std::int32_t {
    Ok = 0,
    NullHandle = 1,
    StaleHandle = 2,
    ConcurrentCall = 3,
    NullBuffer = 4,
    NonDirectBuffer = 5,
    BufferTooSmall = 6,
    InvalidMagic = 7,
    UnsupportedVersion = 8,
    UnexpectedMessageKind = 9,
    MalformedLength = 10,
    InvalidEnum = 11,
    NonFiniteValue = 12,
    DuplicateEvidenceIdentifier = 13,
    PendingJniException = 14,
    AllocationFailure = 15,
    InvalidArgument = 16,
    NativeException = 17,
};

template <typename T>
struct DecodeResult {
    BoundaryStatus status{BoundaryStatus::MalformedLength};
    T value{};
};

struct SnapshotPair {
    StateSnapshot state;
    CovarianceSnapshot covariance;
};

struct PropagationResponse {
    BoundaryStatus boundary_status{BoundaryStatus::Ok};
    PropagationResult result;
    SnapshotPair snapshots;
};

struct MeasurementResponse {
    BoundaryStatus boundary_status{BoundaryStatus::Ok};
    MeasurementResult result;
    SnapshotPair snapshots;
};

struct SnapshotResponse {
    BoundaryStatus boundary_status{BoundaryStatus::Ok};
    SnapshotPair snapshots;
};

std::vector<std::byte> encodeInitialState(const InitialState& value);
std::vector<std::byte> encodeImuBatch(const ImuBatch& value);
std::vector<std::byte> encodeMeasurement(const MeasurementInput& value);
std::vector<std::byte> encodePropagationResponse(const PropagationResponse& value);
std::vector<std::byte> encodeMeasurementResponse(const MeasurementResponse& value);
std::vector<std::byte> encodeSnapshotResponse(const SnapshotResponse& value);

DecodeResult<InitialState> decodeInitialState(std::span<const std::byte> bytes);
DecodeResult<ImuBatch> decodeImuBatch(std::span<const std::byte> bytes);
DecodeResult<MeasurementInput> decodeMeasurement(std::span<const std::byte> bytes);
DecodeResult<PropagationResponse> decodePropagationResponse(std::span<const std::byte> bytes);
DecodeResult<MeasurementResponse> decodeMeasurementResponse(std::span<const std::byte> bytes);
DecodeResult<SnapshotResponse> decodeSnapshotResponse(std::span<const std::byte> bytes);

BoundaryStatus guardedCall(bool pending_jni_exception,
                           const std::function<BoundaryStatus()>& operation) noexcept;

class HandleRegistry {
public:
    std::pair<BoundaryStatus, std::uint64_t> create(std::span<const std::byte> initial_state);
    BoundaryStatus destroy(std::uint64_t handle);
    std::pair<BoundaryStatus, std::vector<std::byte>> propagate(
        std::uint64_t handle, std::span<const std::byte> batch);
    std::pair<BoundaryStatus, std::vector<std::byte>> update(
        std::uint64_t handle, std::span<const std::byte> measurement);
    std::pair<BoundaryStatus, std::vector<std::byte>> snapshot(std::uint64_t handle);

private:
    class Entry;
    std::shared_ptr<Entry> find(std::uint64_t handle) const;

    mutable std::mutex registry_mutex_;
    std::unordered_map<std::uint64_t, std::shared_ptr<Entry>> entries_;
    std::uint64_t next_handle_{1};
};

const char* toString(BoundaryStatus status);

}  // namespace sih26168::navigation::jni
