"""Deterministic classical baselines for matched GNSS-blackout evaluation.

The module intentionally has no third-party dependencies. Coordinates are converted
to a local tangent-plane approximation, and every baseline consumes the same truth
samples and blackout mask.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True)
class Sample:
    time_s: float
    latitude_deg: float
    longitude_deg: float
    speed_mps: float
    heading_deg: float


@dataclass(frozen=True)
class Point:
    east_m: float
    north_m: float


def to_local(samples: Sequence[Sample]) -> list[Point]:
    if not samples:
        return []
    lat0 = math.radians(samples[0].latitude_deg)
    lon0 = math.radians(samples[0].longitude_deg)
    cos_lat0 = math.cos(lat0)
    return [
        Point(
            EARTH_RADIUS_M * (math.radians(s.longitude_deg) - lon0) * cos_lat0,
            EARTH_RADIUS_M * (math.radians(s.latitude_deg) - lat0),
        )
        for s in samples
    ]


def _step(point: Point, speed_mps: float, heading_deg: float, dt_s: float) -> Point:
    heading = math.radians(heading_deg)
    return Point(
        point.east_m + speed_mps * math.sin(heading) * dt_s,
        point.north_m + speed_mps * math.cos(heading) * dt_s,
    )


def hold_last_position(samples: Sequence[Sample], masked: Sequence[bool]) -> list[Point]:
    """Zero-order hold; the minimum-information matched baseline."""
    truth = to_local(samples)
    result: list[Point] = []
    last_visible: Point | None = None
    for point, is_masked in zip(truth, masked, strict=True):
        if not is_masked:
            last_visible = point
        result.append(last_visible if last_visible is not None else point)
    return result


def constant_velocity(samples: Sequence[Sample], masked: Sequence[bool]) -> list[Point]:
    """Propagate last visible GNSS speed and heading during each blackout."""
    truth = to_local(samples)
    result: list[Point] = []
    position: Point | None = None
    speed = 0.0
    heading = 0.0
    previous_time: float | None = None
    for sample, point, is_masked in zip(samples, truth, masked, strict=True):
        if not is_masked or position is None or previous_time is None:
            position = point
            speed = max(0.0, sample.speed_mps)
            heading = sample.heading_deg
        else:
            position = _step(position, speed, heading, max(0.0, sample.time_s - previous_time))
        result.append(position)
        previous_time = sample.time_s
    return result


def constant_turn_rate(samples: Sequence[Sample], masked: Sequence[bool]) -> list[Point]:
    """Propagate speed and a last-observed finite-difference heading rate."""
    truth = to_local(samples)
    result: list[Point] = []
    position: Point | None = None
    speed = 0.0
    heading = 0.0
    turn_rate = 0.0
    previous_time: float | None = None
    previous_visible_heading: float | None = None
    previous_visible_time: float | None = None
    for sample, point, is_masked in zip(samples, truth, masked, strict=True):
        if not is_masked:
            if previous_visible_heading is not None and previous_visible_time is not None:
                dt = sample.time_s - previous_visible_time
                delta = (sample.heading_deg - previous_visible_heading + 180.0) % 360.0 - 180.0
                if dt > 0:
                    turn_rate = delta / dt
            position = point
            speed = max(0.0, sample.speed_mps)
            heading = sample.heading_deg
            previous_visible_heading = heading
            previous_visible_time = sample.time_s
        elif position is None or previous_time is None:
            position = point
        else:
            dt = max(0.0, sample.time_s - previous_time)
            heading = (heading + turn_rate * dt) % 360.0
            position = _step(position, speed, heading, dt)
        result.append(position)
        previous_time = sample.time_s
    return result


BASELINES = {
    "hold": hold_last_position,
    "constant_velocity": constant_velocity,
    "constant_turn_rate": constant_turn_rate,
}


def errors_m(prediction: Iterable[Point], truth: Iterable[Point]) -> list[float]:
    return [math.hypot(p.east_m - t.east_m, p.north_m - t.north_m) for p, t in zip(prediction, truth, strict=True)]

