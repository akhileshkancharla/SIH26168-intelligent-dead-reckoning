"""Metadata gate for a minimal causal IMU feature window.

Metadata must be supplied by a trusted extractor, not relabelled by a caller.
This does not authenticate sensor hardware or replace the active name firewall.
"""
from __future__ import annotations

import math


MINIMAL_BINDINGS = {
    **{f"imu.accel.{axis}": ("phone_accelerometer", axis, "m/s^2", "body") for axis in "xyz"},
    **{f"imu.gyro.{axis}": ("phone_gyroscope", axis, "rad/s", "body") for axis in "xyz"},
    "imu.dt": ("phone_imu_clock", "dt", "s", "none"),
    "imu.gap_mask": ("phone_imu_quality", "gap_mask", "1", "none"),
    "imu.valid_mask": ("phone_imu_quality", "valid_mask", "1", "none"),
}


def validate_minimal_window(records: list[dict], *, start_ns: int, end_ns: int,
                            clock_id: str) -> None:
    """Validate complete nine-channel samples and every declared dependency.

    Each record includes value, source/field/unit/frame, epoch_ns, clock_id,
    dependency_start_ns, dependency_end_ns and available_at_ns. Dependency
    bounds include all preprocessing inputs; availability accounts for delayed
    delivery. The frozen minimal profile excludes GNSS in every navigation mode.
    """
    def integer(value):
        return type(value) is int and value >= 0

    if not integer(start_ns) or not integer(end_ns) or start_ns > end_ns or not isinstance(clock_id, str) or not clock_id.strip():
        raise ValueError("invalid window or clock")
    if not isinstance(records, list) or not records:
        raise ValueError("nonempty feature records required")
    by_epoch = {}
    previous = {}
    for record in records:
        required = {"name", "value", "source", "field", "unit", "frame", "epoch_ns", "clock_id", "dependency_start_ns", "dependency_end_ns", "available_at_ns"}
        if not isinstance(record, dict) or set(record) != required:
            raise ValueError("record fields must match the provenance contract")
        name = record["name"]
        if not isinstance(name, str) or name not in MINIMAL_BINDINGS:
            raise ValueError("feature outside minimal IMU profile")
        if tuple(record[key] for key in ("source", "field", "unit", "frame")) != MINIMAL_BINDINGS[name]:
            raise ValueError("source mapping, unit or frame mismatch")
        times = [record[key] for key in ("dependency_start_ns", "dependency_end_ns", "epoch_ns", "available_at_ns")]
        if not all(integer(value) for value in times):
            raise ValueError("integer monotonic timestamps required")
        dep_start, dep_end, epoch, available = times
        if record["clock_id"] != clock_id or not start_ns <= dep_start <= dep_end <= epoch <= available <= end_ns:
            raise ValueError("noncausal, unavailable or out-of-window dependency")
        if name in previous and epoch <= previous[name]:
            raise ValueError("duplicate or out-of-order feature sample")
        previous[name] = epoch
        by_epoch.setdefault(epoch, set()).add(name)
        value = record["value"]
        try:
            finite = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("finite numeric feature required")
        if name == "imu.dt" and not 1e-6 <= value <= 0.20:
            raise ValueError("dt outside I-03 bounds")
        if name.endswith("_mask") and (type(value) is not int or value not in (0, 1)):
            raise ValueError("feature masks are binary")
    if any(names != set(MINIMAL_BINDINGS) for names in by_epoch.values()):
        raise ValueError("incomplete synchronized nine-channel sample")
