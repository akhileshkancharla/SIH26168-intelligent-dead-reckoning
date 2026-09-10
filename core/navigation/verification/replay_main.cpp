#include "s2_oracle/navigation_core.hpp"

#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {

struct CsvTable {
    std::unordered_map<std::string, std::size_t> column;
    std::vector<std::vector<std::string>> rows;
};

std::vector<std::string> splitCsvLine(const std::string& line) {
    std::vector<std::string> fields;
    std::stringstream stream(line);
    std::string field;
    while (std::getline(stream, field, ',')) {
        if (!field.empty() && field.back() == '\r') {
            field.pop_back();
        }
        fields.push_back(field);
    }
    if (!line.empty() && line.back() == ',') {
        fields.emplace_back();
    }
    return fields;
}

CsvTable readCsv(const std::string& path) {
    std::ifstream input(path);
    if (!input) {
        throw std::runtime_error("Cannot open CSV: " + path);
    }
    CsvTable table;
    std::string line;
    if (!std::getline(input, line)) {
        throw std::runtime_error("CSV is empty: " + path);
    }
    const auto header = splitCsvLine(line);
    for (std::size_t index = 0; index < header.size(); ++index) {
        table.column.emplace(header[index], index);
    }
    while (std::getline(input, line)) {
        if (!line.empty()) {
            table.rows.push_back(splitCsvLine(line));
        }
    }
    return table;
}

const std::string& value(const CsvTable& table,
                         const std::vector<std::string>& row,
                         const std::string& name) {
    const auto iterator = table.column.find(name);
    if (iterator == table.column.end() || iterator->second >= row.size()) {
        throw std::runtime_error("Missing CSV column: " + name);
    }
    return row[iterator->second];
}

double number(const CsvTable& table,
              const std::vector<std::string>& row,
              const std::string& name) {
    return std::stod(value(table, row, name));
}

std::int64_t integer(const CsvTable& table,
                     const std::vector<std::string>& row,
                     const std::string& name) {
    return std::stoll(value(table, row, name));
}

s2::NominalState readInitialState(const std::string& path) {
    const CsvTable table = readCsv(path);
    if (table.rows.size() != 1) {
        throw std::runtime_error("Initial-state CSV must contain exactly one row");
    }
    const auto& row = table.rows.front();
    s2::NominalState state;
    state.timestamp_ns = integer(table, row, "timestamp_ns");
    for (int axis = 0; axis < 3; ++axis) {
        state.position_n(axis) = number(table, row, "p" + std::to_string(axis));
        state.velocity_n(axis) = number(table, row, "v" + std::to_string(axis));
        state.accel_bias_b(axis) = number(table, row, "ba" + std::to_string(axis));
        state.gyro_bias_b(axis) = number(table, row, "bg" + std::to_string(axis));
    }
    state.q_n_b = s2::quaternionFromWxyz(
        number(table, row, "q0"), number(table, row, "q1"),
        number(table, row, "q2"), number(table, row, "q3"));
    state.covariance.setZero();
    const double sigma_position = number(table, row, "sigma_position");
    const double sigma_velocity = number(table, row, "sigma_velocity");
    const double sigma_attitude = number(table, row, "sigma_attitude");
    const double sigma_accel_bias = number(table, row, "sigma_accel_bias");
    const double sigma_gyro_bias = number(table, row, "sigma_gyro_bias");
    state.covariance.block<3, 3>(s2::kPosition, s2::kPosition).diagonal().setConstant(
        sigma_position * sigma_position);
    state.covariance.block<3, 3>(s2::kVelocity, s2::kVelocity).diagonal().setConstant(
        sigma_velocity * sigma_velocity);
    state.covariance.block<3, 3>(s2::kAttitude, s2::kAttitude).diagonal().setConstant(
        sigma_attitude * sigma_attitude);
    state.covariance.block<3, 3>(s2::kAccelBias, s2::kAccelBias).diagonal().setConstant(
        sigma_accel_bias * sigma_accel_bias);
    state.covariance.block<3, 3>(s2::kGyroBias, s2::kGyroBias).diagonal().setConstant(
        sigma_gyro_bias * sigma_gyro_bias);
    return state;
}

s2::MeasurementKind parseKind(const std::string& text) {
    if (text == "position") {
        return s2::MeasurementKind::Position;
    }
    if (text == "velocity") {
        return s2::MeasurementKind::Velocity;
    }
    if (text == "position_velocity") {
        return s2::MeasurementKind::PositionVelocity;
    }
    throw std::runtime_error("Unknown measurement kind: " + text);
}

void writeStateHeader(std::ofstream& output) {
    output << "timestamp_ns";
    for (const std::string& name : {"p0", "p1", "p2", "v0", "v1", "v2",
                                    "q0", "q1", "q2", "q3", "ba0", "ba1", "ba2",
                                    "bg0", "bg1", "bg2"}) {
        output << ',' << name;
    }
    for (int row = 0; row < 15; ++row) {
        for (int column = 0; column < 15; ++column) {
            output << ",P" << row << '_' << column;
        }
    }
    output << '\n';
}

void writeState(std::ofstream& output, const s2::NominalState& state) {
    output << state.timestamp_ns;
    for (int axis = 0; axis < 3; ++axis) output << ',' << state.position_n(axis);
    for (int axis = 0; axis < 3; ++axis) output << ',' << state.velocity_n(axis);
    output << ',' << state.q_n_b.w() << ',' << state.q_n_b.x()
           << ',' << state.q_n_b.y() << ',' << state.q_n_b.z();
    for (int axis = 0; axis < 3; ++axis) output << ',' << state.accel_bias_b(axis);
    for (int axis = 0; axis < 3; ++axis) output << ',' << state.gyro_bias_b(axis);
    for (int row = 0; row < 15; ++row) {
        for (int column = 0; column < 15; ++column) {
            output << ',' << state.covariance(row, column);
        }
    }
    output << '\n';
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 6) {
            std::cerr << "Usage: s2_replay TRAJECTORY MEASUREMENTS INITIAL STATE_OUT MEAS_OUT\n";
            return 2;
        }
        const CsvTable trajectory = readCsv(argv[1]);
        const CsvTable measurements = readCsv(argv[2]);
        s2::NavigationCore core(readInitialState(argv[3]));

        std::multimap<std::int64_t, const std::vector<std::string>*> measurements_by_time;
        for (const auto& row : measurements.rows) {
            measurements_by_time.emplace(integer(measurements, row, "timestamp_ns"), &row);
        }

        std::ofstream state_output(argv[4]);
        std::ofstream measurement_output(argv[5]);
        if (!state_output || !measurement_output) {
            throw std::runtime_error("Cannot create replay output files");
        }
        state_output << std::setprecision(17);
        measurement_output << std::setprecision(17);
        writeStateHeader(state_output);
        measurement_output << "timestamp_ns,measurement_id,status,accepted,duplicate,dimension,nis";
        for (int index = 0; index < 6; ++index) measurement_output << ",innovation" << index;
        measurement_output << '\n';

        int accepted_measurements = 0;
        int rejected_measurements = 0;
        int duplicate_measurements = 0;
        int gaps = 0;
        for (const auto& row : trajectory.rows) {
            s2::ImuSample sample;
            sample.timestamp_ns = integer(trajectory, row, "timestamp_ns");
            for (int axis = 0; axis < 3; ++axis) {
                const std::string suffix(1, "xyz"[axis]);
                sample.specific_force_b(axis) = number(trajectory, row, "observed_acc_" + suffix);
                sample.angular_rate_b(axis) = number(trajectory, row, "observed_gyro_" + suffix);
            }
            const s2::PropagationResult propagation = core.propagate(sample);
            if (!propagation.accepted) {
                throw std::runtime_error("Fixture propagation rejected: " + propagation.status);
            }
            gaps += propagation.gap_detected ? 1 : 0;

            const auto range = measurements_by_time.equal_range(sample.timestamp_ns);
            for (auto iterator = range.first; iterator != range.second; ++iterator) {
                const auto& measurement_row = *iterator->second;
                s2::GnssMeasurement measurement;
                measurement.timestamp_ns = sample.timestamp_ns;
                measurement.id = value(measurements, measurement_row, "measurement_id");
                measurement.kind = parseKind(value(measurements, measurement_row, "kind"));
                measurement.covariance.setZero();
                for (int index = 0; index < 6; ++index) {
                    measurement.value(index) = number(measurements, measurement_row,
                                                      "z" + std::to_string(index));
                    measurement.covariance(index, index) = number(
                        measurements, measurement_row, "r" + std::to_string(index));
                }
                const s2::MeasurementResult update = core.update(measurement);
                accepted_measurements += update.accepted ? 1 : 0;
                duplicate_measurements += update.duplicate ? 1 : 0;
                rejected_measurements += (!update.accepted && !update.duplicate) ? 1 : 0;
                measurement_output << sample.timestamp_ns << ',' << measurement.id << ','
                                   << update.status << ',' << (update.accepted ? 1 : 0) << ','
                                   << (update.duplicate ? 1 : 0) << ',' << update.dimension << ','
                                   << update.nis;
                for (int index = 0; index < 6; ++index) {
                    measurement_output << ',' << update.innovation(index);
                }
                measurement_output << '\n';
            }
            writeState(state_output, core.state());
        }

        std::cout << "replay_rows=" << trajectory.rows.size()
                  << " gaps=" << gaps
                  << " measurements_accepted=" << accepted_measurements
                  << " measurements_rejected=" << rejected_measurements
                  << " duplicates=" << duplicate_measurements << '\n';
        return 0;
    } catch (const std::exception& exception) {
        std::cerr << "s2_replay failure: " << exception.what() << '\n';
        return 1;
    }
}
