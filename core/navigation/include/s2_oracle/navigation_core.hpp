#pragma once

#include "s2_oracle/math.hpp"
#include "s2_oracle/types.hpp"

#include <unordered_set>

namespace s2 {

PropagationLinearization linearizePropagation(const NominalState& state,
                                              const ImuSample& sample,
                                              double dt_s,
                                              const CoreConfig& config);

NominalState propagateNominalOnly(const NominalState& state,
                                  const ImuSample& sample,
                                  double dt_s,
                                  const CoreConfig& config);

Mat15 resetJacobian(const Vec3& injected_attitude_error);

template<int M>
Eigen::Matrix<double, M, 15> measurementJacobian(MeasurementKind kind) {
    Eigen::Matrix<double, M, 15> H = Eigen::Matrix<double, M, 15>::Zero();
    if constexpr (M == 3) {
        if (kind == MeasurementKind::Position) {
            H.template block<3, 3>(0, kPosition) = Mat3::Identity();
        } else {
            H.template block<3, 3>(0, kVelocity) = Mat3::Identity();
        }
    } else {
        static_assert(M == 6, "Only 3-D and 6-D GNSS measurements are supported");
        H.template block<3, 3>(0, kPosition) = Mat3::Identity();
        H.template block<3, 3>(3, kVelocity) = Mat3::Identity();
    }
    return H;
}

class NavigationCore {
public:
    explicit NavigationCore(NominalState initial_state,
                            CoreConfig config = CoreConfig{});

    const NominalState& state() const { return state_; }
    const CoreConfig& config() const { return config_; }
    std::size_t consumedMeasurementCount() const { return consumed_measurement_ids_.size(); }

    PropagationResult propagate(const ImuSample& sample);
    // Evaluate the same innovation gate as update without consuming evidence
    // or changing the nominal state/covariance.
    MeasurementResult screen(const GnssMeasurement& measurement) const;
    MeasurementResult update(const GnssMeasurement& measurement);

private:
    template<int M>
    MeasurementResult screenFixed(const GnssMeasurement& measurement) const;
    template<int M>
    MeasurementResult updateFixed(const GnssMeasurement& measurement);

    NominalState state_;
    CoreConfig config_;
    std::unordered_set<std::string> consumed_measurement_ids_;
};

}  // namespace s2
