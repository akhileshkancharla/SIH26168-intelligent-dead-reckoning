#!/usr/bin/env python3
"""Read-only analyzer for S1 Android acquisition sessions.

The analyzer consumes JSONL chunks in recorded file order. It never rewrites,
sorts, resamples, interpolates, or otherwise alters raw evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

VERSION = "1.0.0"


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - rank) + ordered[high] * (rank - low)


def describe(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "stddev": None, "min": None, "median": None,
                "p90": None, "p95": None, "p99": None, "p99_9": None, "max": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "stddev": statistics.pstdev(values),
        "min": min(values),
        "median": statistics.median(values),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "p99_9": percentile(values, 0.999),
        "max": max(values),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_manifest(session: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = session / "session_manifest.json"
    errors: list[dict[str, Any]] = []
    if not manifest_path.is_file():
        return {}, [{"code": "manifest_missing", "path": str(manifest_path)}]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for chunk in manifest.get("chunks", []):
        path = session / chunk["path"]
        if not path.is_file():
            errors.append({"code": "chunk_missing", "path": chunk["path"]})
            continue
        if path.stat().st_size != chunk["size"]:
            errors.append({"code": "size_mismatch", "path": chunk["path"]})
        actual = sha256(path)
        if actual != chunk["sha256"]:
            errors.append({"code": "hash_mismatch", "path": chunk["path"], "actual": actual})
    declared = {c["path"] for c in manifest.get("chunks", [])}
    for path in session.glob("chunk_*.jsonl"):
        if path.name not in declared:
            errors.append({"code": "undeclared_chunk", "path": path.name})
    if (session / "INCOMPLETE").exists():
        errors.append({"code": "incomplete_marker_present"})
    return manifest, errors


def read_records(session: Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for chunk in manifest.get("chunks", []):
        path = session / chunk["path"]
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                try:
                    item = json.loads(line)
                    item["_evidence_order"] = len(records)
                    item["_chunk"] = chunk["path"]
                    item["_line"] = line_number
                    records.append(item)
                except json.JSONDecodeError as exc:
                    errors.append({"code": "invalid_json", "path": chunk["path"], "line": line_number,
                                   "message": str(exc)})
    return records, errors


def group_gaps(intervals_ns: list[int], threshold_ns: float) -> dict[str, Any]:
    gaps = [x for x in intervals_ns if x > threshold_ns]
    bands = Counter()
    for gap in gaps:
        ms = gap / 1e6
        if ms < 100:
            bands["threshold_to_100ms"] += 1
        elif ms < 500:
            bands["100_to_500ms"] += 1
        elif ms < 1000:
            bands["500ms_to_1s"] += 1
        elif ms < 5000:
            bands["1_to_5s"] += 1
        else:
            bands["ge_5s"] += 1
    return {"threshold_ns": threshold_ns, "count": len(gaps), "bands": dict(bands),
            "durations_ms": [x / 1e6 for x in gaps]}


def burst_sizes(arrivals: list[int], boundary_ns: int = 2_000_000) -> list[int]:
    if not arrivals:
        return []
    sizes: list[int] = []
    current = 1
    for a, b in zip(arrivals, arrivals[1:]):
        if b - a <= boundary_ns:
            current += 1
        else:
            sizes.append(current)
            current = 1
    sizes.append(current)
    return sizes


def analyze_stream(name: str, records: list[dict[str, Any]], requested_rate_hz: float | None) -> dict[str, Any]:
    source = [int(r["source_timestamp_ns"]) for r in records if isinstance(r.get("source_timestamp_ns"), int)]
    arrival = [int(r["callback_arrival_timestamp_ns"]) for r in records if isinstance(r.get("callback_arrival_timestamp_ns"), int)]
    intervals = [b - a for a, b in zip(source, source[1:])]
    positive = [x for x in intervals if x > 0]
    duration_ns = (max(source) - min(source)) if len(source) > 1 else 0
    delivered_rate_hz = ((len(source) - 1) / (duration_ns / 1e9)) if duration_ns > 0 else None
    rates = [1e9 / x for x in positive]
    median_interval = statistics.median(positive) if positive else 0
    gap_threshold = max(100_000_000, 3 * median_interval) if median_interval else 100_000_000
    latencies = [
        (r["callback_arrival_timestamp_ns"] - r["source_timestamp_ns"]) / 1e6
        for r in records
        if isinstance(r.get("callback_arrival_timestamp_ns"), int) and isinstance(r.get("source_timestamp_ns"), int)
    ]
    sequences = [r.get("sequence") for r in records if isinstance(r.get("sequence"), int)]
    sequence_anomalies = sum(1 for a, b in zip(sequences, sequences[1:]) if b != a + 1)
    bursts = burst_sizes(arrival)
    return {
        "stream": name,
        "sample_count": len(records),
        "duration_s": duration_ns / 1e9,
        "requested_rate_hz": requested_rate_hz,
        "delivered_rate_hz": delivered_rate_hz,
        "interval_ms": describe([x / 1e6 for x in positive]),
        "effective_rate_hz": describe(rates),
        "duplicate_timestamps": sum(1 for x in intervals if x == 0),
        "non_monotonic_timestamps": sum(1 for x in intervals if x < 0),
        "callback_reordering": sum(1 for x in intervals if x < 0),
        "sequence_anomalies": sequence_anomalies,
        "gaps": group_gaps(positive, gap_threshold),
        "source_to_arrival_latency_ms": describe(latencies),
        "delivery_bursts": {
            "boundary_ms": 2.0,
            "burst_count": len(bursts),
            "size": describe([float(x) for x in bursts]),
            "multi_event_bursts": sum(1 for x in bursts if x > 1),
        },
    }


def state_at(events: list[tuple[int, Any]], timestamp: int, default: Any = "unknown") -> Any:
    state = default
    for event_time, value in events:
        if event_time > timestamp:
            break
        state = value
    return state


def comparisons(records: list[dict[str, Any]], stream_records: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    screen_events = sorted([
        (r["source_timestamp_ns"], r.get("interactive")) for r in records
        if r.get("record_type") == "screen_state" and isinstance(r.get("source_timestamp_ns"), int)
    ])
    thermal_events = sorted([
        (r["source_timestamp_ns"], r.get("thermal_status")) for r in records
        if r.get("record_type") == "thermal_state" and isinstance(r.get("source_timestamp_ns"), int)
    ])
    output: dict[str, Any] = {}
    for stream, rows in stream_records.items():
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            ts = row.get("source_timestamp_ns")
            if not isinstance(ts, int):
                continue
            screen = state_at(screen_events, ts)
            thermal = state_at(thermal_events, ts)
            buckets.setdefault(f"screen={screen};thermal={thermal}", []).append(row)
        output[stream] = {key: analyze_stream(stream, subset, None) for key, subset in buckets.items()}
    lifecycle_times = [r["source_timestamp_ns"] for r in records
                       if r.get("record_type") == "lifecycle" and isinstance(r.get("source_timestamp_ns"), int)]
    transition_window_count = sum(
        1 for r in records if isinstance(r.get("source_timestamp_ns"), int)
        and any(abs(r["source_timestamp_ns"] - t) <= 5_000_000_000 for t in lifecycle_times)
    )
    return {"screen_and_thermal": output, "lifecycle_transition_window_s": 5,
            "records_near_lifecycle_transition": transition_window_count}


def battery_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [r for r in records if r.get("record_type") == "battery_state" and isinstance(r.get("fraction"), (int, float))]
    if len(rows) < 2:
        return {"evidence_sufficient": False, "reason": "fewer_than_two_battery_observations"}
    first, last = rows[0], rows[-1]
    duration_h = (last["source_timestamp_ns"] - first["source_timestamp_ns"]) / 3.6e12
    drop = first["fraction"] - last["fraction"]
    return {
        "evidence_sufficient": duration_h > 0,
        "start_fraction": first["fraction"], "end_fraction": last["fraction"],
        "fraction_change": -drop, "duration_h": duration_h,
        "percentage_points_per_hour": (drop * 100 / duration_h) if duration_h > 0 else None,
        "charging_observed": any(bool(r.get("charging")) for r in rows),
        "caution": "Coarse OS battery-level evidence; not component-level power attribution.",
    }


def gnss_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    fixes = [r for r in records if r.get("record_type") == "location_fix"]
    providers = Counter(str(r.get("provider", "missing")) for r in fixes)
    ages = [r["age_at_callback_ns"] / 1e6 for r in fixes if isinstance(r.get("age_at_callback_ns"), int)]
    if len(fixes) > 1:
        times = [r["source_elapsed_realtime_ns"] for r in fixes if isinstance(r.get("source_elapsed_realtime_ns"), int)]
        duration = (max(times) - min(times)) / 1e9 if len(times) > 1 else 0
        rate = (len(times) - 1) / duration if duration > 0 else None
    else:
        rate = None
    missing = {field: sum(1 for r in fixes if not r.get(field)) for field in
               ("has_horizontal_accuracy", "has_vertical_accuracy", "has_speed", "has_bearing")}
    return {"fix_count": len(fixes), "fix_rate_hz": rate, "fix_age_ms": describe(ages),
            "provider_distribution": dict(providers), "missing_availability_fields": missing,
            "gnss_status_is_not_position": True}


def requested_rates(records: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    metadata = next((r for r in records if r.get("record_type") == "session_metadata"), {})
    requested = metadata.get("requested_sampling", {})
    period = requested.get("sensor_period_us")
    sensor_rate = 1e6 / period if isinstance(period, (int, float)) and period > 0 else None
    location_ms = requested.get("location_min_time_ms")
    location_rate = 1000 / location_ms if isinstance(location_ms, (int, float)) and location_ms > 0 else None
    return sensor_rate, location_rate


def analyze_session(session: Path) -> dict[str, Any]:
    manifest, validation_errors = validate_manifest(session)
    records, parse_errors = read_records(session, manifest)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record.get("stream", "missing")), []).append(record)
    sensor_request, location_request = requested_rates(records)
    metrics = {}
    for stream, rows in grouped.items():
        requested = sensor_request if stream.startswith("sensor:") else location_request if stream.startswith("location:") else None
        metrics[stream] = analyze_stream(stream, rows, requested)
    return {
        "analyzer_version": VERSION,
        "raw_evidence_modified": False,
        "session_path": str(session),
        "session_id": manifest.get("session_id"),
        "session_complete": bool(manifest.get("complete")) and not (session / "INCOMPLETE").exists(),
        "manifest_and_parse_errors": validation_errors + parse_errors,
        "record_count": len(records),
        "streams": metrics,
        "comparisons": comparisons(records, grouped),
        "battery": battery_summary(records),
        "gnss_location": gnss_summary(records),
    }


def write_csv(result: dict[str, Any], target: Path) -> None:
    columns = ["stream", "sample_count", "duration_s", "requested_rate_hz", "delivered_rate_hz",
               "median_interval_ms", "p95_interval_ms", "p99_9_interval_ms", "duplicates",
               "non_monotonic", "callback_reordering", "gap_count"]
    with target.open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        for stream, metric in sorted(result["streams"].items()):
            writer.writerow({
                "stream": stream, "sample_count": metric["sample_count"], "duration_s": metric["duration_s"],
                "requested_rate_hz": metric["requested_rate_hz"], "delivered_rate_hz": metric["delivered_rate_hz"],
                "median_interval_ms": metric["interval_ms"]["median"], "p95_interval_ms": metric["interval_ms"]["p95"],
                "p99_9_interval_ms": metric["interval_ms"]["p99_9"], "duplicates": metric["duplicate_timestamps"],
                "non_monotonic": metric["non_monotonic_timestamps"], "callback_reordering": metric["callback_reordering"],
                "gap_count": metric["gaps"]["count"],
            })


def escape_xml(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_svg(result: dict[str, Any], target: Path) -> None:
    sensors = [(name, m) for name, m in sorted(result["streams"].items()) if name.startswith("sensor:")]
    width, row_h = 1000, 52
    height = max(180, 120 + len(sensors) * row_h)
    rates = [m["delivered_rate_hz"] or 0 for _, m in sensors]
    scale = 700 / max(rates + [1])
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<text x="25" y="35" font-family="sans-serif" font-size="22" font-weight="bold">S1 delivered sensor rates (measured)</text>',
             '<text x="25" y="62" font-family="sans-serif" font-size="13">Bars use source timestamp intervals; requested rates are labels, not observations.</text>']
    for index, (name, metric) in enumerate(sensors):
        y = 100 + index * row_h
        rate = metric["delivered_rate_hz"] or 0
        lines += [f'<text x="25" y="{y + 18}" font-family="monospace" font-size="12">{escape_xml(name[:58])}</text>',
                  f'<rect x="360" y="{y}" width="{rate * scale:.1f}" height="24" fill="#0B57D0"/>',
                  f'<text x="{370 + rate * scale:.1f}" y="{y + 18}" font-family="sans-serif" font-size="12">{rate:.3f} Hz</text>']
    lines.append('</svg>')
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def materialize_input(source: Path, temporary: Path) -> Path:
    if source.is_dir():
        return source
    if not zipfile.is_zipfile(source):
        raise ValueError("Input must be a session directory or ZIP")
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            destination = (temporary / member.filename).resolve()
            if temporary.resolve() not in destination.parents and destination != temporary.resolve():
                raise ValueError(f"Unsafe ZIP member: {member.filename}")
        archive.extractall(temporary)
    candidates = list(temporary.rglob("session_manifest.json"))
    if len(candidates) != 1:
        raise ValueError("ZIP must contain exactly one session_manifest.json")
    return candidates[0].parent


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="s1_analyzer_") as temp_name:
        session = materialize_input(args.session, Path(temp_name))
        result = analyze_session(session)
    (args.output / "analysis_results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_csv(result, args.output / "stream_statistics.csv")
    write_svg(result, args.output / "delivered_rates.svg")
    print(json.dumps({"session_id": result["session_id"], "records": result["record_count"],
                      "errors": len(result["manifest_and_parse_errors"]), "output": str(args.output)}))
    return 0 if not result["manifest_and_parse_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
