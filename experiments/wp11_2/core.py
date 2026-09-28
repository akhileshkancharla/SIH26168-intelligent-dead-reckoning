"""Deterministic, journey-safe primitives for the WP-11.2 ridge pipeline."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import math
from pathlib import Path


VERSION = "wp11.2-v2"
DEFAULT_FEATURES = (
    "accelerometer_x",
    "accelerometer_y",
    "accelerometer_z",
    "gyroscope_x",
    "gyroscope_y",
    "gyroscope_z",
    "gravity_x",
    "gravity_y",
    "gravity_z",
    "orientation_x",
    "orientation_y",
    "orientation_z",
)
FORBIDDEN_FEATURE_TOKENS = (
    "latitude",
    "longitude",
    "gnss",
    "gps",
    "ground_truth",
    "target",
    "label",
    "position",
    "speed",
    "velocity",
    "vbox",
    "wheel",
    "can_",
)


@dataclass(frozen=True)
class TrainingConfig:
    features: tuple[str, ...]
    target: str
    ridge: float = 1e-6
    train_fraction: float = 0.8
    group_column: str = "session_id"
    time_column: str = "timestamp_ns"

    def validate(self) -> None:
        if not self.features or len(set(self.features)) != len(self.features):
            raise ValueError("features must be non-empty and unique")
        if self.target in self.features:
            raise ValueError("target cannot also be a feature")
        if not self.target:
            raise ValueError("target must be non-empty")
        if not 0 < self.train_fraction < 1:
            raise ValueError("train_fraction must be between 0 and 1")
        if not math.isfinite(self.ridge) or self.ridge <= 0:
            raise ValueError("ridge must be finite and greater than zero")
        if not self.group_column or not self.time_column:
            raise ValueError("group and time columns must be non-empty")
        reserved = {self.target, self.group_column, self.time_column}
        overlap = sorted(reserved.intersection(self.features))
        if overlap:
            raise ValueError("reserved columns cannot be features: " + ", ".join(overlap))
        forbidden = [
            feature
            for feature in self.features
            if any(token in feature.lower() for token in FORBIDDEN_FEATURE_TOKENS)
        ]
        if forbidden:
            raise ValueError("forbidden/leaky features: " + ", ".join(forbidden))


@dataclass(frozen=True)
class Sample:
    group_id: str
    timestamp_ns: int
    features: tuple[float, ...]
    target: float


def load(path: Path, config: TrainingConfig) -> list[Sample]:
    config.validate()
    required = set(config.features) | {
        config.target,
        config.group_column,
        config.time_column,
    }
    rows: list[Sample] = []
    last_timestamp_by_group: dict[str, int] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise ValueError("missing columns: " + ", ".join(missing))
        for line_number, row in enumerate(reader, 2):
            group_id = (row.get(config.group_column) or "").strip()
            if not group_id:
                raise ValueError(f"empty group ID on line {line_number}")
            try:
                timestamp_ns = int(row[config.time_column])
                features = tuple(float(row[name]) for name in config.features)
                target = float(row[config.target])
            except (TypeError, ValueError) as error:
                raise ValueError(f"invalid numeric value on line {line_number}") from error
            if timestamp_ns < 0:
                raise ValueError(f"negative timestamp on line {line_number}")
            if not all(math.isfinite(value) for value in (*features, target)):
                raise ValueError(f"non-finite value on line {line_number}")
            previous = last_timestamp_by_group.get(group_id)
            if previous is not None and timestamp_ns <= previous:
                raise ValueError(
                    f"timestamps must increase within each group (line {line_number})"
                )
            last_timestamp_by_group[group_id] = timestamp_ns
            rows.append(Sample(group_id, timestamp_ns, features, target))
    if len(rows) < 3:
        raise ValueError("at least three rows are required")
    if len(last_timestamp_by_group) < 2:
        raise ValueError("at least two journey groups are required")
    return rows


def split_by_group(
    rows: list[Sample], train_fraction: float
) -> tuple[list[Sample], list[Sample], tuple[str, ...], tuple[str, ...]]:
    groups: list[str] = []
    seen_groups: set[str] = set()
    for row in rows:
        if row.group_id not in seen_groups:
            seen_groups.add(row.group_id)
            groups.append(row.group_id)
    # File order is authoritative. Session timestamps are boot-scoped and must
    # not be compared across journey groups.
    split_index = max(1, min(len(groups) - 1, int(len(groups) * train_fraction)))
    train_groups = tuple(groups[:split_index])
    validation_groups = tuple(groups[split_index:])
    train_set = set(train_groups)
    validation_set = set(validation_groups)
    if train_set.intersection(validation_set):
        raise AssertionError("journey groups overlap across the split")
    train_rows = [row for row in rows if row.group_id in train_set]
    validation_rows = [row for row in rows if row.group_id in validation_set]
    return train_rows, validation_rows, train_groups, validation_groups


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [matrix[index][:] + [vector[index]] for index in range(size)]
    scale = max((abs(value) for row in matrix for value in row), default=0.0)
    if not math.isfinite(scale) or scale == 0:
        raise ValueError("invalid or singular system")
    tolerance = scale * 1e-12
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= tolerance:
            raise ValueError("ill-conditioned system; increase ridge or review features")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column])
            ]
    result = [augmented[index][-1] for index in range(size)]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("fit produced non-finite coefficients")
    return result


def fit(rows: list[Sample], ridge: float) -> list[float]:
    width = len(rows[0].features) + 1
    matrix = [[0.0] * width for _ in range(width)]
    vector = [0.0] * width
    for sample in rows:
        values = [1.0, *sample.features]
        for row in range(width):
            vector[row] += values[row] * sample.target
            for column in range(width):
                matrix[row][column] += values[row] * values[column]
    for diagonal in range(1, width):
        matrix[diagonal][diagonal] += ridge
    if not all(math.isfinite(value) for row in matrix for value in row):
        raise ValueError("fit matrix contains non-finite values")
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("fit vector contains non-finite values")
    return solve(matrix, vector)
