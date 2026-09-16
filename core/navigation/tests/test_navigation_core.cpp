#include "s2_oracle/navigation_core.hpp"

#include <Eigen/Eigenvalues>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

constexpr double kPi = 3.141592653589793238462643383279502884;

struct TestRecord {
    std::string name;
    bool passed{false};
    std::string detail;
};

struct JacobianReport {
    int propagation_cases{0};
    double propagation_max_absolute{0.0};
    double propagation_max_relative{0.0};
    int propagation_row{0};
    int propagation_column{0};
    int propagation_case{0};
    double propagation_analytic{0.0};
    double propagation_numeric{0.0};
    int measurement_cases{0};
    double measurement_max_absolute{0.0};
    double measurement_max_relative{0.0};
    int measurement_row{0};
    int measurement_column{0};
    std::string measurement_kind;
    double measurement_analytic{0.0};
    double measurement_numeric{0.0};
};

JacobianReport g_jacobian_report;

void require(bool condition, const std::string& detail) {
    if (!condition) {
        throw std::runtime_error(detail);
    }
}

void requireNear(double actual, double expected, double tolerance, const std::string& label) {
    if (!std::isfinite(actual) || std::abs(actual - expected) > tolerance) {
        std::ostringstream message;
        message << std::setprecision(17) << label << ": actual=" << actual
                << " expected=" << expected << " tolerance=" << tolerance;
        throw std::runtime_error(message.str());
    }
}

void requireVectorNear(const s2::Vec3& actual, const s2::Vec3& expected,
                       double tolerance, const std::string& label) {
    const double error = (actual - expected).norm();
    if (!std::isfinite(error) || error > tolerance) {
        std::ostringstream message;
        message << std::setprecision(17) << label << ": norm_error=" << error
                << " actual=" << actual.transpose()
                << " expected=" << expected.transpose();
        throw std::runtime_error(message.str());
    }
}

double minimumEigenvalue(const s2::Mat15& covariance) {
    Eigen::SelfAdjointEigenSolver<s2::Mat15> solver(covariance);
    require(solver.info() == Eigen::Success, "Eigenvalue decomposition failed");
    return solver.eigenvalues().minCoeff();
}

s2::CoreConfig zeroNoiseConfig() {
    s2::CoreConfig config;
    config.accel_noise_density = 0.0;
    config.gyro_noise_density = 0.0;
    config.accel_bias_rw_density = 0.0;
    config.gyro_bias_rw_density = 0.0;
    return config;
}

s2::NominalState zeroState() {
    s2::NominalState state;
    state.covariance.setZero();
    return state;
}

s2::GnssMeasurement makeMeasurement(const std::string& id,
                                    std::int64_t timestamp_ns,
                                    s2::MeasurementKind kind,
                                    const s2::Vec6& value,
                                    const s2::Vec6& variance) {
    s2::GnssMeasurement measurement;
    measurement.id = id;
    measurement.timestamp_ns = timestamp_ns;
    measurement.kind = kind;
    measurement.value = value;
    measurement.covariance.setZero();
    measurement.covariance.diagonal() = variance;
    return measurement;
}

void propagateConstant(s2::NavigationCore& core, int steps, double dt,
                       const s2::Vec3& force, const s2::Vec3& rate) {
    std::int64_t timestamp = core.state().timestamp_ns;
    const std::int64_t increment = static_cast<std::int64_t>(std::llround(dt * 1.0e9));
    for (int step = 0; step < steps; ++step) {
        timestamp += increment;
        const auto result = core.propagate(s2::ImuSample{timestamp, force, rate});
        require(result.accepted, "Propagation rejected: " + result.status);
    }
}

std::string stateBlock(int index) {
    if (index < 3) return "position";
    if (index < 6) return "velocity";
    if (index < 9) return "attitude";
    if (index < 12) return "accel_bias";
    return "gyro_bias";
}

double perturbationStep(int column) {
    if (column < 6) return 1.0e-6;
    if (column < 9) return 1.0e-7;
    if (column < 12) return 1.0e-6;
    return 1.0e-6;
}

JacobianReport runJacobianChecks() {
    JacobianReport report;
    const std::vector<s2::Vec3> orientations = {
        s2::Vec3(0.0, 0.0, 0.0),
        s2::Vec3(0.35, -0.42, 0.71),
        s2::Vec3(-0.60, 0.25, 1.20),
        s2::Vec3(0.10, 0.80, -1.00),
        s2::Vec3(-0.30, -0.55, 2.00),
    };
    const std::vector<double> intervals = {0.005, 0.010, 0.020, 0.013, 0.008};

    const s2::CoreConfig config = zeroNoiseConfig();
    for (std::size_t case_index = 0; case_index < orientations.size(); ++case_index) {
        s2::NominalState state = zeroState();
        state.position_n = s2::Vec3(4.0, -2.0, 0.5);
        state.velocity_n = s2::Vec3(7.0, 1.5, -0.2);
        state.q_n_b = s2::quaternionExp(orientations[case_index]);
        state.accel_bias_b = s2::Vec3(0.02, -0.03, 0.015);
        state.gyro_bias_b = s2::Vec3(0.001, -0.002, 0.0007);
        const double dt = intervals[case_index];
        const s2::ImuSample sample{
            static_cast<std::int64_t>(std::llround(dt * 1.0e9)),
            s2::Vec3(0.6, -0.4, -9.3),
            s2::Vec3(0.08, -0.04, 0.22),
        };
        const s2::Mat15 analytic =
            s2::linearizePropagation(state, sample, dt, config).phi;
        const s2::NominalState nominal_output =
            s2::propagateNominalOnly(state, sample, dt, config);
        s2::Mat15 numeric = s2::Mat15::Zero();
        for (int column = 0; column < 15; ++column) {
            const double step = perturbationStep(column);
            s2::Vec15 plus_error = s2::Vec15::Zero();
            s2::Vec15 minus_error = s2::Vec15::Zero();
            plus_error(column) = step;
            minus_error(column) = -step;
            s2::NominalState plus_state = state;
            s2::NominalState minus_state = state;
            s2::injectError(plus_state, plus_error);
            s2::injectError(minus_state, minus_error);
            const s2::NominalState plus_output =
                s2::propagateNominalOnly(plus_state, sample, dt, config);
            const s2::NominalState minus_output =
                s2::propagateNominalOnly(minus_state, sample, dt, config);
            numeric.col(column) =
                (s2::stateError(nominal_output, plus_output)
                 - s2::stateError(nominal_output, minus_output)) / (2.0 * step);
        }

        for (int row = 0; row < 15; ++row) {
            for (int column = 0; column < 15; ++column) {
                const double absolute = std::abs(analytic(row, column) - numeric(row, column));
                const double denominator = std::max(
                    std::abs(analytic(row, column)), std::abs(numeric(row, column)));
                if (absolute > report.propagation_max_absolute) {
                    report.propagation_max_absolute = absolute;
                    report.propagation_row = row;
                    report.propagation_column = column;
                    report.propagation_case = static_cast<int>(case_index);
                    report.propagation_analytic = analytic(row, column);
                    report.propagation_numeric = numeric(row, column);
                }
                // Relative error is meaningful only for materially non-zero
                // elements. Absolute error above is retained for all 225
                // elements, including structural zeros and tiny dt^3 terms.
                if (denominator >= 1.0e-6) {
                    report.propagation_max_relative = std::max(
                        report.propagation_max_relative, absolute / denominator);
                }
            }
        }
        ++report.propagation_cases;
    }

    for (const auto kind : {s2::MeasurementKind::Position,
                            s2::MeasurementKind::Velocity,
                            s2::MeasurementKind::PositionVelocity}) {
        const int dimension = kind == s2::MeasurementKind::PositionVelocity ? 6 : 3;
        for (std::size_t orientation_index = 0; orientation_index < orientations.size(); ++orientation_index) {
            s2::NominalState state = zeroState();
            state.position_n = s2::Vec3(2.0, -1.0, 0.3);
            state.velocity_n = s2::Vec3(4.0, 0.5, -0.1);
            state.q_n_b = s2::quaternionExp(orientations[orientation_index]);
            Eigen::Matrix<double, 6, 15> analytic6 = Eigen::Matrix<double, 6, 15>::Zero();
            if (dimension == 3) {
                analytic6.topRows<3>() = s2::measurementJacobian<3>(kind);
            } else {
                analytic6 = s2::measurementJacobian<6>(kind);
            }
            Eigen::Matrix<double, 6, 15> numeric = Eigen::Matrix<double, 6, 15>::Zero();
            auto measurementValue = [kind](const s2::NominalState& input) {
                s2::Vec6 output = s2::Vec6::Zero();
                if (kind == s2::MeasurementKind::Position) output.head<3>() = input.position_n;
                else if (kind == s2::MeasurementKind::Velocity) output.head<3>() = input.velocity_n;
                else {
                    output.head<3>() = input.position_n;
                    output.tail<3>() = input.velocity_n;
                }
                return output;
            };
            for (int column = 0; column < 15; ++column) {
                const double step = perturbationStep(column);
                s2::Vec15 plus_error = s2::Vec15::Zero();
                s2::Vec15 minus_error = s2::Vec15::Zero();
                plus_error(column) = step;
                minus_error(column) = -step;
                s2::NominalState plus = state;
                s2::NominalState minus = state;
                s2::injectError(plus, plus_error);
                s2::injectError(minus, minus_error);
                numeric.col(column) = (measurementValue(plus) - measurementValue(minus)) / (2.0 * step);
            }
            for (int row = 0; row < dimension; ++row) {
                for (int column = 0; column < 15; ++column) {
                    const double absolute = std::abs(analytic6(row, column) - numeric(row, column));
                    const double denominator = std::max(
                        std::abs(analytic6(row, column)), std::abs(numeric(row, column)));
                    if (absolute > report.measurement_max_absolute) {
                        report.measurement_max_absolute = absolute;
                        report.measurement_row = row;
                        report.measurement_column = column;
                        report.measurement_kind = kind == s2::MeasurementKind::Position
                                                    ? "position"
                                                    : (kind == s2::MeasurementKind::Velocity
                                                           ? "velocity" : "position_velocity");
                        report.measurement_analytic = analytic6(row, column);
                        report.measurement_numeric = numeric(row, column);
                    }
                    if (denominator >= 1.0e-6) {
                        report.measurement_max_relative = std::max(
                            report.measurement_max_relative, absolute / denominator);
                    }
                }
            }
            ++report.measurement_cases;
        }
    }
    return report;
}

std::string jsonEscape(const std::string& input) {
    std::string output;
    for (const char character : input) {
        if (character == '"' || character == '\\') output.push_back('\\');
        if (character == '\n') output += "\\n";
        else output.push_back(character);
    }
    return output;
}

void writeTestResults(const std::string& path, const std::vector<TestRecord>& records) {
    const int passed = static_cast<int>(std::count_if(
        records.begin(), records.end(), [](const TestRecord& record) { return record.passed; }));
    std::ofstream output(path);
    require(static_cast<bool>(output), "Cannot write C++ test result JSON");
    output << std::setprecision(17)
           << "{\n  \"schema_version\": 1,\n  \"language\": \"C++20\",\n"
           << "  \"total\": " << records.size() << ",\n"
           << "  \"passed\": " << passed << ",\n"
           << "  \"failed\": " << (static_cast<int>(records.size()) - passed) << ",\n"
           << "  \"skipped\": 0,\n  \"tests\": [\n";
    for (std::size_t index = 0; index < records.size(); ++index) {
        const auto& record = records[index];
        output << "    {\"name\": \"" << jsonEscape(record.name) << "\", "
               << "\"status\": \"" << (record.passed ? "passed" : "failed") << "\", "
               << "\"detail\": \"" << jsonEscape(record.detail) << "\"}"
               << (index + 1 == records.size() ? "\n" : ",\n");
    }
    output << "  ]\n}\n";
}

void writeJacobianResults(const std::string& path, const JacobianReport& report) {
    std::ofstream output(path);
    require(static_cast<bool>(output), "Cannot write C++ Jacobian result JSON");
    output << std::setprecision(17)
           << "{\n  \"schema_version\": 1,\n  \"language\": \"C++20\",\n"
           << "  \"perturbation_convention\": \"right-multiplicative attitude; additive p,v,bias; central finite differences\",\n"
           << "  \"step_sizes\": {\"position_m\": 1e-6, \"velocity_mps\": 1e-6, "
              "\"attitude_rad\": 1e-7, \"accel_bias_mps2\": 1e-6, \"gyro_bias_radps\": 1e-6},\n"
           << "  \"relative_error_definition\": \"absolute error divided by max absolute analytic/numeric value only where that denominator is at least 1e-6; absolute error covers every element\",\n"
           << "  \"propagation\": {\n"
           << "    \"cases\": " << report.propagation_cases << ",\n"
           << "    \"max_absolute_error\": " << report.propagation_max_absolute << ",\n"
           << "    \"max_relative_error\": " << report.propagation_max_relative << ",\n"
           << "    \"max_error_element\": {\"case\": " << report.propagation_case
           << ", \"row\": " << report.propagation_row
           << ", \"column\": " << report.propagation_column
           << ", \"row_block\": \"" << stateBlock(report.propagation_row)
           << "\", \"column_block\": \"" << stateBlock(report.propagation_column)
           << "\", \"analytic\": " << report.propagation_analytic
           << ", \"finite_difference\": " << report.propagation_numeric << "}\n  },\n"
           << "  \"measurement\": {\n"
           << "    \"cases\": " << report.measurement_cases << ",\n"
           << "    \"max_absolute_error\": " << report.measurement_max_absolute << ",\n"
           << "    \"max_relative_error\": " << report.measurement_max_relative << ",\n"
           << "    \"max_error_element\": {\"kind\": \"" << report.measurement_kind
           << "\", \"row\": " << report.measurement_row
           << ", \"column\": " << report.measurement_column
           << ", \"column_block\": \"" << stateBlock(report.measurement_column)
           << "\", \"analytic\": " << report.measurement_analytic
           << ", \"finite_difference\": " << report.measurement_numeric << "}\n  }\n}\n";
}

}  // namespace

int main(int argc, char** argv) {
    const std::string test_json = argc > 1 ? argv[1] : "cpp_test_results.json";
    const std::string jacobian_json = argc > 2 ? argv[2] : "cpp_jacobian_results.json";
    std::vector<TestRecord> records;
    auto run = [&records](const std::string& name, const std::function<void()>& test) {
        TestRecord record;
        record.name = name;
        try {
            test();
            record.passed = true;
            record.detail = "all assertions satisfied";
        } catch (const std::exception& exception) {
            record.passed = false;
            record.detail = exception.what();
        }
        std::cout << (record.passed ? "PASS " : "FAIL ") << name;
        if (!record.passed) std::cout << ": " << record.detail;
        std::cout << '\n';
        records.push_back(std::move(record));
    };

    run("frame.identity_rotation", [] {
        require((s2::quaternionExp(s2::Vec3::Zero()).toRotationMatrix()
                 - s2::Mat3::Identity()).norm() < 1.0e-15, "Identity mismatch");
    });
    run("frame.known_90_degree_rotations", [] {
        const s2::Vec3 x = s2::Vec3::UnitX();
        requireVectorNear(s2::so3Exp(s2::Vec3(0.0, 0.0, kPi / 2.0)) * x,
                          s2::Vec3::UnitY(), 1.0e-12, "z rotation");
        requireVectorNear(s2::so3Exp(s2::Vec3(0.0, kPi / 2.0, 0.0)) * x,
                          -s2::Vec3::UnitZ(), 1.0e-12, "y rotation");
    });
    run("frame.composition_order", [] {
        const auto first = s2::quaternionExp(s2::Vec3(0.2, 0.0, 0.0));
        const auto second = s2::quaternionExp(s2::Vec3(0.0, 0.0, -0.4));
        const auto composed = s2::canonicalQuaternion(first * second);
        require((composed.toRotationMatrix()
                 - first.toRotationMatrix() * second.toRotationMatrix()).norm() < 1.0e-14,
                "Quaternion composition order mismatch");
    });
    run("frame.inverse_transformation", [] {
        const s2::Mat3 rotation = s2::so3Exp(s2::Vec3(0.4, -0.2, 0.7));
        const s2::Vec3 vector(1.2, -4.0, 0.5);
        requireVectorNear(rotation.transpose() * (rotation * vector), vector, 1.0e-12,
                          "Inverse rotation");
    });
    run("frame.quaternion_to_matrix_parity", [] {
        const s2::Vec3 rotation_vector(0.2, -0.7, 1.1);
        require((s2::quaternionExp(rotation_vector).toRotationMatrix()
                 - s2::so3Exp(rotation_vector)).norm() < 1.0e-12,
                "Quaternion/matrix exponential mismatch");
    });
    run("frame.matrix_to_quaternion_parity", [] {
        const s2::Mat3 rotation = s2::so3Exp(s2::Vec3(-0.5, 0.3, 1.0));
        const Eigen::Quaterniond reconstructed(rotation);
        require((s2::canonicalQuaternion(reconstructed).toRotationMatrix() - rotation).norm()
                    < 1.0e-12,
                "Matrix/quaternion reconstruction mismatch");
    });
    run("frame.small_angle_injection", [] {
        s2::NominalState nominal = zeroState();
        nominal.q_n_b = s2::quaternionExp(s2::Vec3(0.3, -0.2, 0.5));
        s2::NominalState injected = nominal;
        s2::Vec15 correction = s2::Vec15::Zero();
        correction.segment<3>(s2::kAttitude) = s2::Vec3(1.0e-5, -2.0e-5, 0.5e-5);
        s2::injectError(injected, correction);
        requireVectorNear(s2::stateError(nominal, injected).segment<3>(s2::kAttitude),
                          correction.segment<3>(s2::kAttitude), 1.0e-11,
                          "Small-angle injection");
    });
    run("frame.reset_consistency", [] {
        s2::NominalState original = zeroState();
        original.q_n_b = s2::quaternionExp(s2::Vec3(0.2, 0.1, -0.3));
        const s2::Vec3 correction(0.04, -0.03, 0.02);
        const s2::Vec3 residual(2.0e-6, -1.0e-6, 3.0e-6);
        s2::NominalState updated = original;
        s2::Vec15 correction15 = s2::Vec15::Zero();
        correction15.segment<3>(s2::kAttitude) = correction;
        s2::injectError(updated, correction15);
        s2::NominalState truth = original;
        s2::Vec15 truth_error = s2::Vec15::Zero();
        truth_error.segment<3>(s2::kAttitude) = correction + residual;
        s2::injectError(truth, truth_error);
        const s2::Vec3 reset_residual =
            s2::stateError(updated, truth).segment<3>(s2::kAttitude);
        requireVectorNear(reset_residual, s2::rightJacobianSo3(correction) * residual,
                          2.0e-10, "Reset Jacobian");
    });

    run("mechanization.stationary_specific_force_cancellation", [] {
        s2::NavigationCore core(zeroState(), zeroNoiseConfig());
        propagateConstant(core, 500, 0.01, s2::Vec3(0.0, 0.0, -9.80665), s2::Vec3::Zero());
        require(core.state().position_n.norm() < 1.0e-12, "Stationary position drift");
        require(core.state().velocity_n.norm() < 1.0e-12, "Stationary velocity drift");
    });
    run("mechanization.constant_velocity", [] {
        auto state = zeroState();
        state.velocity_n = s2::Vec3(7.0, -1.0, 0.2);
        s2::NavigationCore core(state, zeroNoiseConfig());
        propagateConstant(core, 300, 0.01, s2::Vec3(0.0, 0.0, -9.80665), s2::Vec3::Zero());
        requireVectorNear(core.state().position_n, state.velocity_n * 3.0, 1.0e-10,
                          "Constant-velocity position");
        requireVectorNear(core.state().velocity_n, state.velocity_n, 1.0e-12,
                          "Constant velocity");
    });
    run("mechanization.constant_acceleration", [] {
        s2::NavigationCore core(zeroState(), zeroNoiseConfig());
        propagateConstant(core, 200, 0.01, s2::Vec3(1.0, 0.0, -9.80665), s2::Vec3::Zero());
        requireNear(core.state().velocity_n.x(), 2.0, 1.0e-10, "Acceleration velocity");
        requireNear(core.state().position_n.x(), 2.0, 1.0e-10, "Acceleration position");
    });
    run("mechanization.constant_radius_turn", [] {
        auto state = zeroState();
        const double speed = 5.0;
        const double yaw_rate = 0.25;
        state.velocity_n = s2::Vec3(speed, 0.0, 0.0);
        s2::NavigationCore core(state, zeroNoiseConfig());
        propagateConstant(core, 800, 0.005,
                          s2::Vec3(0.0, speed * yaw_rate, -9.80665),
                          s2::Vec3(0.0, 0.0, yaw_rate));
        const double time = 4.0;
        const s2::Vec3 expected_position(speed / yaw_rate * std::sin(yaw_rate * time),
                                         speed / yaw_rate * (1.0 - std::cos(yaw_rate * time)), 0.0);
        const s2::Vec3 expected_velocity(speed * std::cos(yaw_rate * time),
                                         speed * std::sin(yaw_rate * time), 0.0);
        requireVectorNear(core.state().position_n, expected_position, 3.0e-5,
                          "Turn position");
        requireVectorNear(core.state().velocity_n, expected_velocity, 3.0e-6,
                          "Turn velocity");
    });
    run("mechanization.bias_free_truth", [] {
        auto state = zeroState();
        state.q_n_b = s2::quaternionExp(s2::Vec3(0.1, -0.2, 0.3));
        const s2::ImuSample sample{10'000'000, s2::Vec3(0.4, 0.2, -9.6),
                                   s2::Vec3(0.01, -0.03, 0.2)};
        const auto expected = s2::propagateNominalOnly(state, sample, 0.01, zeroNoiseConfig());
        s2::NavigationCore core(state, zeroNoiseConfig());
        require(core.propagate(sample).accepted, "Bias-free propagation rejected");
        requireVectorNear(core.state().position_n, expected.position_n, 1.0e-15,
                          "Bias-free position");
        require(s2::rotationDistance(core.state().q_n_b, expected.q_n_b) < 1.0e-14,
                "Bias-free attitude");
    });
    run("mechanization.known_constant_biases", [] {
        auto state = zeroState();
        state.accel_bias_b = s2::Vec3(0.04, -0.02, 0.03);
        state.gyro_bias_b = s2::Vec3(0.002, -0.001, 0.003);
        s2::NavigationCore core(state, zeroNoiseConfig());
        propagateConstant(core, 400, 0.01,
                          s2::Vec3(0.04, -0.02, -9.80665 + 0.03),
                          state.gyro_bias_b);
        require(core.state().position_n.norm() < 1.0e-10, "Bias correction position drift");
        require(core.state().velocity_n.norm() < 1.0e-11, "Bias correction velocity drift");
    });
    run("mechanization.irregular_dt", [] {
        s2::NavigationCore core(zeroState(), zeroNoiseConfig());
        const std::vector<double> intervals = {0.007, 0.011, 0.009, 0.013, 0.008, 0.012};
        std::int64_t timestamp = 0;
        double elapsed = 0.0;
        for (int repeat = 0; repeat < 30; ++repeat) {
            for (const double interval : intervals) {
                const auto increment = static_cast<std::int64_t>(std::llround(interval * 1.0e9));
                timestamp += increment;
                elapsed += interval;
                require(core.propagate({timestamp, s2::Vec3(0.6, 0.0, -9.80665),
                                        s2::Vec3::Zero()}).accepted,
                        "Irregular interval rejected");
            }
        }
        requireNear(core.state().velocity_n.x(), 0.6 * elapsed, 1.0e-11,
                    "Irregular velocity");
        requireNear(core.state().position_n.x(), 0.3 * elapsed * elapsed, 1.0e-10,
                    "Irregular position");
    });
    run("mechanization.quaternion_norm", [] {
        s2::NavigationCore core(zeroState(), zeroNoiseConfig());
        propagateConstant(core, 5000, 0.001, s2::Vec3(0.0, 0.0, -9.80665),
                          s2::Vec3(0.3, -0.2, 0.8));
        requireNear(core.state().q_n_b.norm(), 1.0, 2.0e-15, "Quaternion norm");
    });
    run("mechanization.invalid_timestamps_rejected", [] {
        s2::NavigationCore core(zeroState(), zeroNoiseConfig());
        require(core.propagate({10'000'000, s2::Vec3(0.0, 0.0, -9.80665),
                                s2::Vec3::Zero()}).accepted, "Initial valid sample rejected");
        require(!core.propagate({10'000'000, s2::Vec3::Zero(), s2::Vec3::Zero()}).accepted,
                "Duplicate timestamp accepted");
        require(!core.propagate({9'000'000, s2::Vec3::Zero(), s2::Vec3::Zero()}).accepted,
                "Backward timestamp accepted");
        require(!core.propagate({500'000'000, s2::Vec3::Zero(), s2::Vec3::Zero()}).accepted,
                "Oversized dt accepted");
    });
    run("mechanization.missing_sample_gap_flagged", [] {
        s2::NavigationCore core(zeroState(), zeroNoiseConfig());
        const auto result = core.propagate(
            {40'000'000, s2::Vec3(0.0, 0.0, -9.80665), s2::Vec3::Zero()});
        require(result.accepted && result.gap_detected && result.status == "accepted_gap",
                "Valid missing-sample gap not flagged");
    });
    run("mechanization.deterministic_replay", [] {
        s2::NavigationCore first(zeroState());
        s2::NavigationCore second(zeroState());
        std::int64_t timestamp = 0;
        for (int index = 0; index < 200; ++index) {
            timestamp += 10'000'000;
            const s2::Vec3 force(0.01 * std::sin(index), 0.02 * std::cos(index), -9.80665);
            const s2::Vec3 rate(0.001, -0.002, 0.01 * std::sin(0.2 * index));
            require(first.propagate({timestamp, force, rate}).accepted, "First replay failed");
            require(second.propagate({timestamp, force, rate}).accepted, "Second replay failed");
        }
        require(s2::stateError(first.state(), second.state()).norm() == 0.0,
                "Nominal replay is not bit-deterministic");
        require((first.state().covariance - second.state().covariance).norm() == 0.0,
                "Covariance replay is not bit-deterministic");
    });

    run("covariance.symmetry", [] {
        auto state = zeroState();
        state.covariance = s2::Mat15::Identity() * 0.1;
        s2::NavigationCore core(state);
        propagateConstant(core, 200, 0.01, s2::Vec3(0.2, -0.1, -9.7),
                          s2::Vec3(0.01, 0.02, -0.03));
        require((core.state().covariance - core.state().covariance.transpose()).cwiseAbs().maxCoeff()
                    < 1.0e-14,
                "Covariance lost symmetry");
    });
    run("covariance.positive_semidefinite", [] {
        auto state = zeroState();
        state.covariance = s2::Mat15::Identity() * 0.1;
        s2::NavigationCore core(state);
        propagateConstant(core, 300, 0.01, s2::Vec3(0.2, 0.1, -9.8),
                          s2::Vec3(0.02, -0.01, 0.03));
        require(minimumEigenvalue(core.state().covariance) >= -1.0e-12,
                "Materially negative covariance eigenvalue");
    });
    run("covariance.growth", [] {
        auto state = zeroState();
        state.covariance = s2::Mat15::Identity() * 1.0e-6;
        const double initial_trace = state.covariance.trace();
        s2::NavigationCore core(state);
        propagateConstant(core, 100, 0.01, s2::Vec3(0.0, 0.0, -9.80665), s2::Vec3::Zero());
        require(core.state().covariance.trace() > initial_trace, "Covariance did not grow");
    });
    run("covariance.bias_random_walk_growth", [] {
        auto state = zeroState();
        state.covariance.setZero();
        auto config = zeroNoiseConfig();
        config.accel_bias_rw_density = 0.002;
        config.gyro_bias_rw_density = 0.0003;
        s2::NavigationCore core(state, config);
        require(core.propagate({100'000'000, s2::Vec3(0.0, 0.0, -9.80665),
                                s2::Vec3::Zero()}).accepted,
                "RW propagation failed");
        requireNear(core.state().covariance(s2::kAccelBias, s2::kAccelBias),
                    0.002 * 0.002 * 0.1, 1.0e-18, "Accel bias RW variance");
        requireNear(core.state().covariance(s2::kGyroBias, s2::kGyroBias),
                    0.0003 * 0.0003 * 0.1, 1.0e-20, "Gyro bias RW variance");
    });
    run("covariance.joseph_update", [] {
        auto state = zeroState();
        state.timestamp_ns = 1'000'000'000;
        state.covariance = s2::Mat15::Identity();
        s2::NavigationCore core(state, zeroNoiseConfig());
        s2::Vec6 value = s2::Vec6::Zero();
        value.head<3>() = s2::Vec3(0.2, -0.1, 0.05);
        s2::Vec6 variance = s2::Vec6::Ones();
        const auto result = core.update(makeMeasurement(
            "pos", state.timestamp_ns, s2::MeasurementKind::Position, value, variance));
        require(result.accepted, "Joseph update measurement rejected");
        require(core.state().covariance(0, 0) < 1.0, "Position variance did not decrease");
        require(minimumEigenvalue(core.state().covariance) >= -1.0e-13,
                "Joseph covariance not PSD");
    });
    run("covariance.reset_covariance_behavior", [] {
        s2::Mat15 covariance = s2::Mat15::Identity();
        covariance.block<3, 3>(s2::kPosition, s2::kAttitude) = s2::Mat3::Identity() * 0.1;
        covariance.block<3, 3>(s2::kAttitude, s2::kPosition) = s2::Mat3::Identity() * 0.1;
        const s2::Mat15 reset = s2::resetJacobian(s2::Vec3(0.1, -0.08, 0.04));
        const s2::Mat15 transformed = reset * covariance * reset.transpose();
        require((transformed - transformed.transpose()).cwiseAbs().maxCoeff() < 1.0e-14,
                "Reset covariance asymmetric");
        require(minimumEigenvalue(transformed) >= -1.0e-13,
                "Reset covariance not PSD");
        require((transformed - covariance).norm() > 1.0e-4,
                "Nonzero attitude reset left covariance unchanged");
    });
    run("covariance.no_nan_or_infinity", [] {
        auto state = zeroState();
        state.covariance = s2::Mat15::Identity() * 0.01;
        s2::NavigationCore core(state);
        propagateConstant(core, 500, 0.005, s2::Vec3(0.3, -0.1, -9.5),
                          s2::Vec3(0.1, 0.05, -0.2));
        require(core.state().covariance.allFinite(), "Non-finite covariance");
        require(core.state().position_n.allFinite(), "Non-finite state");
    });
    run("covariance.no_negative_variance", [] {
        auto state = zeroState();
        state.covariance = s2::Mat15::Identity() * 0.01;
        s2::NavigationCore core(state);
        propagateConstant(core, 500, 0.005, s2::Vec3(0.3, -0.1, -9.5),
                          s2::Vec3(0.1, 0.05, -0.2));
        require(core.state().covariance.diagonal().minCoeff() >= -1.0e-14,
                "Negative variance");
    });

    run("measurement.position_only_update", [] {
        auto state = zeroState(); state.timestamp_ns = 100; state.covariance = s2::Mat15::Identity();
        s2::NavigationCore core(state, zeroNoiseConfig());
        s2::Vec6 value = s2::Vec6::Zero(); value.head<3>() = s2::Vec3(0.5, -0.2, 0.1);
        const auto result = core.update(makeMeasurement("p", 100, s2::MeasurementKind::Position,
                                                       value, s2::Vec6::Ones()));
        require(result.accepted && result.dimension == 3, "Position update failed");
        require(core.state().position_n.norm() > 0.0, "Position state unchanged");
    });
    run("measurement.velocity_only_update", [] {
        auto state = zeroState(); state.timestamp_ns = 100; state.covariance = s2::Mat15::Identity();
        s2::NavigationCore core(state, zeroNoiseConfig());
        s2::Vec6 value = s2::Vec6::Zero(); value.head<3>() = s2::Vec3(0.3, 0.1, -0.1);
        const auto result = core.update(makeMeasurement("v", 100, s2::MeasurementKind::Velocity,
                                                       value, s2::Vec6::Ones()));
        require(result.accepted && result.dimension == 3, "Velocity update failed");
        require(core.state().velocity_n.norm() > 0.0, "Velocity state unchanged");
    });
    run("measurement.combined_update", [] {
        auto state = zeroState(); state.timestamp_ns = 100; state.covariance = s2::Mat15::Identity();
        s2::NavigationCore core(state, zeroNoiseConfig());
        s2::Vec6 value; value << 0.2, -0.1, 0.0, 0.3, 0.1, 0.0;
        const auto result = core.update(makeMeasurement(
            "pv", 100, s2::MeasurementKind::PositionVelocity, value, s2::Vec6::Ones()));
        require(result.accepted && result.dimension == 6, "Combined update failed");
    });
    run("measurement.correct_nis_dimensions", [] {
        auto state3 = zeroState(); state3.timestamp_ns = 100; state3.covariance = s2::Mat15::Identity();
        auto state6 = state3;
        s2::NavigationCore core3(state3, zeroNoiseConfig());
        s2::NavigationCore core6(state6, zeroNoiseConfig());
        s2::Vec6 value = s2::Vec6::Constant(0.1);
        require(core3.update(makeMeasurement("m3", 100, s2::MeasurementKind::Position,
                                             value, s2::Vec6::Ones())).dimension == 3,
                "Position NIS degrees of freedom incorrect");
        require(core6.update(makeMeasurement("m6", 100, s2::MeasurementKind::PositionVelocity,
                                             value, s2::Vec6::Ones())).dimension == 6,
                "Combined NIS degrees of freedom incorrect");
    });
    run("measurement.accepted_inlier", [] {
        auto state = zeroState(); state.timestamp_ns = 100; state.covariance = s2::Mat15::Identity();
        s2::NavigationCore core(state, zeroNoiseConfig());
        s2::Vec6 value = s2::Vec6::Zero(); value(0) = 0.2;
        const auto result = core.update(makeMeasurement("inlier", 100,
            s2::MeasurementKind::Position, value, s2::Vec6::Ones()));
        require(result.accepted && result.nis < core.config().gate_chi2_3,
                "Inlier not accepted");
    });
    run("measurement.rejected_outlier", [] {
        auto state = zeroState(); state.timestamp_ns = 100; state.covariance = s2::Mat15::Identity() * 0.01;
        s2::NavigationCore core(state, zeroNoiseConfig());
        s2::Vec6 value = s2::Vec6::Zero(); value.head<3>() = s2::Vec3(100.0, -100.0, 30.0);
        const auto result = core.update(makeMeasurement("outlier", 100,
            s2::MeasurementKind::Position, value, s2::Vec6::Constant(0.01)));
        require(!result.accepted && result.status == "rejected_nis_gate",
                "Outlier accepted");
    });
    run("measurement.duplicate_id_rejection", [] {
        auto state = zeroState(); state.timestamp_ns = 100; state.covariance = s2::Mat15::Identity();
        s2::NavigationCore core(state, zeroNoiseConfig());
        const auto measurement = makeMeasurement("same", 100, s2::MeasurementKind::Position,
                                                 s2::Vec6::Zero(), s2::Vec6::Ones());
        require(core.update(measurement).accepted, "First evidence rejected");
        const auto duplicate = core.update(measurement);
        require(duplicate.duplicate && !duplicate.accepted,
                "Duplicate evidence not rejected");
        require(core.consumedMeasurementCount() == 1, "Duplicate changed ID set");
    });
    run("measurement.reacquisition_update", [] {
        auto state = zeroState(); state.covariance = s2::Mat15::Identity() * 0.2;
        s2::NavigationCore core(state, zeroNoiseConfig());
        propagateConstant(core, 50, 0.02, s2::Vec3(0.0, 0.0, -9.80665), s2::Vec3::Zero());
        s2::Vec6 value = s2::Vec6::Zero();
        const auto result = core.update(makeMeasurement("return_good", core.state().timestamp_ns,
            s2::MeasurementKind::PositionVelocity, value, s2::Vec6::Ones()));
        require(result.accepted, "Good reacquisition rejected");
    });
    run("measurement.biased_return_rejected", [] {
        auto state = zeroState(); state.covariance = s2::Mat15::Identity() * 0.05;
        s2::NavigationCore core(state, zeroNoiseConfig());
        propagateConstant(core, 50, 0.02, s2::Vec3(0.0, 0.0, -9.80665), s2::Vec3::Zero());
        const auto before = core.state();
        s2::Vec6 value; value << 40.0, -30.0, 10.0, 8.0, -5.0, 2.0;
        const auto result = core.update(makeMeasurement("return_bad", core.state().timestamp_ns,
            s2::MeasurementKind::PositionVelocity, value, s2::Vec6::Constant(0.1)));
        require(!result.accepted && result.status == "rejected_nis_gate",
                "Biased return accepted");
        require(s2::stateError(before, core.state()).norm() == 0.0,
                "Rejected return changed nominal state");
    });

    run("jacobian.propagation_manifold_finite_difference", [] {
        g_jacobian_report = runJacobianChecks();
        require(g_jacobian_report.propagation_max_absolute < 5.0e-7,
                "Propagation Jacobian max absolute error too large");
        require(g_jacobian_report.propagation_max_relative < 5.0e-4,
                "Propagation Jacobian max relative error too large");
    });
    run("jacobian.measurement_manifold_finite_difference", [] {
        if (g_jacobian_report.propagation_cases == 0) g_jacobian_report = runJacobianChecks();
        require(g_jacobian_report.measurement_max_absolute < 2.0e-9,
                "Measurement Jacobian max absolute error too large");
        require(g_jacobian_report.measurement_max_relative < 2.0e-5,
                "Measurement Jacobian max relative error too large");
    });

    try {
        writeTestResults(test_json, records);
        if (g_jacobian_report.propagation_cases == 0) g_jacobian_report = runJacobianChecks();
        writeJacobianResults(jacobian_json, g_jacobian_report);
    } catch (const std::exception& exception) {
        std::cerr << "Failed to write result files: " << exception.what() << '\n';
        return 2;
    }

    const int failed = static_cast<int>(std::count_if(
        records.begin(), records.end(), [](const TestRecord& record) { return !record.passed; }));
    std::cout << "C++ tests: total=" << records.size()
              << " passed=" << (static_cast<int>(records.size()) - failed)
              << " failed=" << failed << " skipped=0\n";
    return failed == 0 ? 0 : 1;
}
