#include "sih26168/navigation_jni.hpp"

#include <jni.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <span>
#include <vector>

namespace api = sih26168::navigation::jni;

namespace {

api::HandleRegistry& registry() {
    static api::HandleRegistry value;
    return value;
}

struct DirectBuffer {
    api::BoundaryStatus status{api::BoundaryStatus::Ok};
    std::span<std::byte> bytes;
};

DirectBuffer directBuffer(JNIEnv* environment, jobject buffer) {
    if (environment->ExceptionCheck()) return {api::BoundaryStatus::PendingJniException, {}};
    if (buffer == nullptr) return {api::BoundaryStatus::NullBuffer, {}};
    void* address = environment->GetDirectBufferAddress(buffer);
    if (environment->ExceptionCheck()) return {api::BoundaryStatus::PendingJniException, {}};
    const jlong capacity = environment->GetDirectBufferCapacity(buffer);
    if (environment->ExceptionCheck()) return {api::BoundaryStatus::PendingJniException, {}};
    if (address == nullptr || capacity < 0) return {api::BoundaryStatus::NonDirectBuffer, {}};
    if (static_cast<std::uint64_t>(capacity) > api::kMaximumMessageBytes) {
        return {api::BoundaryStatus::MalformedLength, {}};
    }
    return {api::BoundaryStatus::Ok,
            {static_cast<std::byte*>(address), static_cast<std::size_t>(capacity)}};
}

void writeU32(std::span<std::byte> output, std::size_t offset, std::uint32_t value) {
    for (std::size_t index = 0; index < 4; ++index) {
        output[offset + index] = static_cast<std::byte>((value >> (index * 8U)) & 0xffU);
    }
}

void writeU64(std::span<std::byte> output, std::size_t offset, std::uint64_t value) {
    for (std::size_t index = 0; index < 8; ++index) {
        output[offset + index] = static_cast<std::byte>((value >> (index * 8U)) & 0xffU);
    }
}

api::BoundaryStatus copyResponse(const std::vector<std::byte>& response,
                                 std::span<std::byte> output) {
    if (response.size() > output.size()) return api::BoundaryStatus::BufferTooSmall;
    std::copy(response.begin(), response.end(), output.begin());
    return api::BoundaryStatus::Ok;
}

template <typename Operation>
jint invoke(JNIEnv* environment, jlong handle, jobject input_buffer, jobject output_buffer,
            Operation operation) noexcept {
    return static_cast<jint>(api::guardedCall(environment->ExceptionCheck(), [&] {
        const DirectBuffer input = directBuffer(environment, input_buffer);
        if (input.status != api::BoundaryStatus::Ok) return input.status;
        const DirectBuffer output = directBuffer(environment, output_buffer);
        if (output.status != api::BoundaryStatus::Ok) return output.status;
        const auto [status, response] = operation(
            static_cast<std::uint64_t>(handle), std::span<const std::byte>(input.bytes));
        return status == api::BoundaryStatus::Ok ? copyResponse(response, output.bytes) : status;
    }));
}

}  // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_org_sih26168_navigation_NativeNavigationJni_create(
    JNIEnv* environment, jclass, jobject input_buffer, jobject result_buffer) noexcept {
    jlong handle_result = 0;
    const auto status = api::guardedCall(environment->ExceptionCheck(), [&] {
        const DirectBuffer input = directBuffer(environment, input_buffer);
        if (input.status != api::BoundaryStatus::Ok) return input.status;
        const DirectBuffer output = directBuffer(environment, result_buffer);
        if (output.status != api::BoundaryStatus::Ok) return output.status;
        if (output.bytes.size() < 12U) return api::BoundaryStatus::BufferTooSmall;
        const auto [create_status, handle] = registry().create(
            std::span<const std::byte>(input.bytes));
        writeU32(output.bytes, 0, static_cast<std::uint32_t>(create_status));
        writeU64(output.bytes, 4, handle);
        if (create_status == api::BoundaryStatus::Ok) handle_result = static_cast<jlong>(handle);
        return create_status;
    });
    if (status != api::BoundaryStatus::Ok) handle_result = -static_cast<jlong>(status);
    return handle_result;
}

extern "C" JNIEXPORT jint JNICALL
Java_org_sih26168_navigation_NativeNavigationJni_destroy(
    JNIEnv* environment, jclass, jlong handle) noexcept {
    return static_cast<jint>(api::guardedCall(environment->ExceptionCheck(), [&] {
        return registry().destroy(static_cast<std::uint64_t>(handle));
    }));
}

extern "C" JNIEXPORT jint JNICALL
Java_org_sih26168_navigation_NativeNavigationJni_propagate(
    JNIEnv* environment, jclass, jlong handle, jobject input, jobject output) noexcept {
    return invoke(environment, handle, input, output,
                  [](std::uint64_t value, std::span<const std::byte> bytes) {
                      return registry().propagate(value, bytes);
                  });
}

extern "C" JNIEXPORT jint JNICALL
Java_org_sih26168_navigation_NativeNavigationJni_update(
    JNIEnv* environment, jclass, jlong handle, jobject input, jobject output) noexcept {
    return invoke(environment, handle, input, output,
                  [](std::uint64_t value, std::span<const std::byte> bytes) {
                      return registry().update(value, bytes);
                  });
}

extern "C" JNIEXPORT jint JNICALL
Java_org_sih26168_navigation_NativeNavigationJni_snapshot(
    JNIEnv* environment, jclass, jlong handle, jobject output_buffer) noexcept {
    return static_cast<jint>(api::guardedCall(environment->ExceptionCheck(), [&] {
        const DirectBuffer output = directBuffer(environment, output_buffer);
        if (output.status != api::BoundaryStatus::Ok) return output.status;
        const auto [status, response] = registry().snapshot(static_cast<std::uint64_t>(handle));
        return status == api::BoundaryStatus::Ok ? copyResponse(response, output.bytes) : status;
    }));
}
