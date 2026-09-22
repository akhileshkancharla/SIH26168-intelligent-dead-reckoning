#include "sih26168/navigation_jni.hpp"

#include <limits>
#include <new>
#include <stdexcept>

namespace sih26168::navigation::jni {

class HandleRegistry::Entry {
public:
    explicit Entry(const InitialState& initial_state) : core(initial_state) {}

    std::mutex call_mutex;
    bool active{true};
    NavigationCore core;
};

namespace {

SnapshotPair snapshotsFor(NavigationCore& core) {
    return {core.stateSnapshot(), core.covarianceSnapshot()};
}

BoundaryStatus exceptionStatus() noexcept {
    try {
        throw;
    } catch (const std::bad_alloc&) {
        return BoundaryStatus::AllocationFailure;
    } catch (const std::invalid_argument&) {
        return BoundaryStatus::InvalidArgument;
    } catch (const std::exception&) {
        return BoundaryStatus::NativeException;
    } catch (...) {
        return BoundaryStatus::NativeException;
    }
}

}  // namespace

BoundaryStatus guardedCall(bool pending_jni_exception,
                           const std::function<BoundaryStatus()>& operation) noexcept {
    if (pending_jni_exception) return BoundaryStatus::PendingJniException;
    try {
        return operation();
    } catch (...) {
        return exceptionStatus();
    }
}

std::shared_ptr<HandleRegistry::Entry> HandleRegistry::find(std::uint64_t handle) const {
    if (handle == 0) return {};
    std::scoped_lock lock(registry_mutex_);
    const auto iterator = entries_.find(handle);
    return iterator == entries_.end() ? std::shared_ptr<Entry>{} : iterator->second;
}

std::pair<BoundaryStatus, std::uint64_t> HandleRegistry::create(
    std::span<const std::byte> initial_state) {
    const auto decoded = decodeInitialState(initial_state);
    if (decoded.status != BoundaryStatus::Ok) return {decoded.status, 0};
    try {
        auto entry = std::make_shared<Entry>(decoded.value);
        std::scoped_lock lock(registry_mutex_);
        if (next_handle_ == 0
            || next_handle_ > static_cast<std::uint64_t>(
                std::numeric_limits<std::int64_t>::max())) {
            return {BoundaryStatus::NativeException, 0};
        }
        const std::uint64_t handle = next_handle_++;
        entries_.emplace(handle, std::move(entry));
        return {BoundaryStatus::Ok, handle};
    } catch (...) {
        return {exceptionStatus(), 0};
    }
}

BoundaryStatus HandleRegistry::destroy(std::uint64_t handle) {
    if (handle == 0) return BoundaryStatus::NullHandle;
    std::scoped_lock lock(registry_mutex_);
    const auto iterator = entries_.find(handle);
    if (iterator == entries_.end()) return BoundaryStatus::StaleHandle;
    std::unique_lock call_lock(iterator->second->call_mutex, std::try_to_lock);
    if (!call_lock.owns_lock()) return BoundaryStatus::ConcurrentCall;
    iterator->second->active = false;
    entries_.erase(iterator);
    return BoundaryStatus::Ok;
}

std::pair<BoundaryStatus, std::vector<std::byte>> HandleRegistry::propagate(
    std::uint64_t handle, std::span<const std::byte> batch) {
    if (handle == 0) return {BoundaryStatus::NullHandle, {}};
    const auto entry = find(handle);
    if (!entry) return {BoundaryStatus::StaleHandle, {}};
    const auto decoded = decodeImuBatch(batch);
    if (decoded.status != BoundaryStatus::Ok) return {decoded.status, {}};
    std::unique_lock lock(entry->call_mutex, std::try_to_lock);
    if (!lock.owns_lock()) return {BoundaryStatus::ConcurrentCall, {}};
    if (!entry->active) return {BoundaryStatus::StaleHandle, {}};
    try {
        PropagationResponse response;
        response.result = entry->core.propagate(decoded.value);
        response.snapshots = snapshotsFor(entry->core);
        return {BoundaryStatus::Ok, encodePropagationResponse(response)};
    } catch (...) {
        return {exceptionStatus(), {}};
    }
}

std::pair<BoundaryStatus, std::vector<std::byte>> HandleRegistry::update(
    std::uint64_t handle, std::span<const std::byte> measurement) {
    if (handle == 0) return {BoundaryStatus::NullHandle, {}};
    const auto entry = find(handle);
    if (!entry) return {BoundaryStatus::StaleHandle, {}};
    const auto decoded = decodeMeasurement(measurement);
    if (decoded.status != BoundaryStatus::Ok) return {decoded.status, {}};
    std::unique_lock lock(entry->call_mutex, std::try_to_lock);
    if (!lock.owns_lock()) return {BoundaryStatus::ConcurrentCall, {}};
    if (!entry->active) return {BoundaryStatus::StaleHandle, {}};
    try {
        MeasurementResponse response;
        response.result = entry->core.update(decoded.value);
        response.snapshots = snapshotsFor(entry->core);
        return {BoundaryStatus::Ok, encodeMeasurementResponse(response)};
    } catch (...) {
        return {exceptionStatus(), {}};
    }
}

std::pair<BoundaryStatus, std::vector<std::byte>> HandleRegistry::snapshot(
    std::uint64_t handle) {
    if (handle == 0) return {BoundaryStatus::NullHandle, {}};
    const auto entry = find(handle);
    if (!entry) return {BoundaryStatus::StaleHandle, {}};
    std::unique_lock lock(entry->call_mutex, std::try_to_lock);
    if (!lock.owns_lock()) return {BoundaryStatus::ConcurrentCall, {}};
    if (!entry->active) return {BoundaryStatus::StaleHandle, {}};
    try {
        SnapshotResponse response;
        response.snapshots = snapshotsFor(entry->core);
        return {BoundaryStatus::Ok, encodeSnapshotResponse(response)};
    } catch (...) {
        return {exceptionStatus(), {}};
    }
}

const char* toString(BoundaryStatus status) {
    switch (status) {
        case BoundaryStatus::Ok: return "ok";
        case BoundaryStatus::NullHandle: return "null_handle";
        case BoundaryStatus::StaleHandle: return "stale_handle";
        case BoundaryStatus::ConcurrentCall: return "concurrent_call";
        case BoundaryStatus::NullBuffer: return "null_buffer";
        case BoundaryStatus::NonDirectBuffer: return "non_direct_buffer";
        case BoundaryStatus::BufferTooSmall: return "buffer_too_small";
        case BoundaryStatus::InvalidMagic: return "invalid_magic";
        case BoundaryStatus::UnsupportedVersion: return "unsupported_version";
        case BoundaryStatus::UnexpectedMessageKind: return "unexpected_message_kind";
        case BoundaryStatus::MalformedLength: return "malformed_length";
        case BoundaryStatus::InvalidEnum: return "invalid_enum";
        case BoundaryStatus::NonFiniteValue: return "non_finite_value";
        case BoundaryStatus::DuplicateEvidenceIdentifier: return "duplicate_evidence_identifier";
        case BoundaryStatus::PendingJniException: return "pending_jni_exception";
        case BoundaryStatus::AllocationFailure: return "allocation_failure";
        case BoundaryStatus::InvalidArgument: return "invalid_argument";
        case BoundaryStatus::NativeException: return "native_exception";
    }
    return "native_exception";
}

}  // namespace sih26168::navigation::jni
