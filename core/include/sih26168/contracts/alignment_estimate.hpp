#pragma once

#include "sih26168/contracts/enums.hpp"

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace sih26168::contracts {

// I-06 Tier-C contract. Covariance is row-major and expressed in rad^2.
// q_v_b_wxyz is the active b-to-v rotation in canonical wxyz form.
struct AlignmentEstimate {
    std::uint64_t sequence{0};
    std::int64_t epoch_ns{0};
    std::array<double, 4> q_v_b_wxyz{1.0, 0.0, 0.0, 0.0};
    std::array<double, 9> covariance_3x3{};
    AlignmentStatusV1 status{AlignmentStatusV1::UNINITIALIZED};
    double observability{0.0};
    std::optional<double> slip_probability{std::nullopt};
    std::string method_id;
    std::vector<std::string> evidence_ids;
    std::string config_id;
};

}  // namespace sih26168::contracts
