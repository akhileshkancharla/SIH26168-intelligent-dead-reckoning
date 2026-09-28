"""Run matched classical baselines on paired IO-VNBD vehicle CSV journeys."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import sys

from baselines import BASELINES, Sample, errors_m, to_local


def _number(row: dict[str, str], contains: str) -> float:
    for key, value in row.items():
        if contains.lower() in key.lower():
            return float(value)
    raise KeyError(f"column containing {contains!r} not found")


def load_vehicle_csv(path: Path, limit: int | None = None) -> list[Sample]:
    samples: list[Sample] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            if limit is not None and index >= limit:
                break
            samples.append(
                Sample(
                    time_s=_number(row, "Time Since Start of Day"),
                    latitude_deg=_number(row, "Latitude"),
                    longitude_deg=_number(row, "Longitude"),
                    speed_mps=_number(row, "Velocity (km/hr)") / 3.6,
                    heading_deg=_number(row, "Heading"),
                )
            )
    if len(samples) < 3:
        raise ValueError("at least three valid samples are required")
    return samples


def periodic_mask(count: int, sample_period_s: float, start_s: float, duration_s: float, spacing_s: float) -> list[bool]:
    if min(sample_period_s, duration_s, spacing_s) <= 0 or duration_s >= spacing_s:
        raise ValueError("mask parameters must be positive and duration < spacing")
    result = []
    for index in range(count):
        elapsed = index * sample_period_s
        result.append(elapsed >= start_s and ((elapsed - start_s) % spacing_s) < duration_s)
    return result


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("no masked samples to summarize")
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "mean_m": statistics.fmean(values),
        "rmse_m": math.sqrt(statistics.fmean(v * v for v in values)),
        "p95_m": ordered[p95_index],
        "max_m": ordered[-1],
        "endpoint_m": values[-1],
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vehicle_csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start-s", type=float, default=60.0)
    parser.add_argument("--duration-s", type=float, default=30.0)
    parser.add_argument("--spacing-s", type=float, default=120.0)
    args = parser.parse_args()

    samples = load_vehicle_csv(args.vehicle_csv, args.limit)
    periods = [b.time_s - a.time_s for a, b in zip(samples, samples[1:]) if b.time_s > a.time_s]
    sample_period = statistics.median(periods)
    masked = periodic_mask(len(samples), sample_period, args.start_s, args.duration_s, args.spacing_s)
    truth = to_local(samples)
    selected = [index for index, flag in enumerate(masked) if flag]
    results = {}
    for name, baseline in BASELINES.items():
        prediction = baseline(samples, masked)
        all_errors = errors_m(prediction, truth)
        results[name] = summarize([all_errors[index] for index in selected])

    report = {
        "scientific_status": "exploratory; not a promotion or safety claim",
        "input": {"path": args.vehicle_csv.name, "sha256": sha256(args.vehicle_csv), "samples": len(samples)},
        "protocol": {
            "sample_period_s": sample_period,
            "start_s": args.start_s,
            "duration_s": args.duration_s,
            "spacing_s": args.spacing_s,
            "masked_samples": len(selected),
            "matched_input_and_mask": True,
        },
        "baselines": results,
        "runtime": {"python": sys.version, "platform": platform.platform()},
        "limitations": [
            "Single-journey execution is smoke evidence only.",
            "Periodic mask is provisional until WP-11.3 freezes the blackout protocol.",
            "No learned model is evaluated in WP-11.1.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

