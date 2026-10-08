"""Evidence-bounded matched comparison for WP-11.4.

This module evaluates already-produced prediction error traces.  It does not
train a model, define a blackout mask, or read private source data.  Those are
owned by the upstream WP-11 tasks.  Every variant must identify the same
dataset manifest, split, mask, and ordered sample IDs so that an apparent
improvement cannot be produced by comparing different evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable


SCHEMA_VERSION = 1
RUNNER_VERSION = "wp11.4-v1"
KINDS = {"baseline", "model", "feature_ablation"}
METRIC_NAMES = ("mean_m", "rmse_m", "p95_m", "max_m", "endpoint_m")


class AblationError(ValueError):
    """Raised when evidence is not safe to compare."""


def _require_text(document: dict[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AblationError(f"{field} must be a non-empty string")
    return value


def _require_sha256(value: str, field: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise AblationError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _finite_nonnegative(values: Iterable[Any], field: str) -> list[float]:
    result: list[float] = []
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AblationError(f"{field}[{index}] must be numeric")
        number = float(value)
        if not math.isfinite(number) or number < 0.0:
            raise AblationError(f"{field}[{index}] must be finite and non-negative")
        result.append(number)
    if not result:
        raise AblationError(f"{field} must not be empty")
    return result


def summarize(errors_m: list[float]) -> dict[str, float]:
    """Return the metric set used by the matched WP-11 comparison."""
    ordered = sorted(errors_m)
    p95_index = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "mean_m": statistics.fmean(errors_m),
        "rmse_m": math.sqrt(statistics.fmean(error * error for error in errors_m)),
        "p95_m": ordered[p95_index],
        "max_m": ordered[-1],
        "endpoint_m": errors_m[-1],
    }


def encode_report(report: dict[str, Any]) -> bytes:
    """Return the canonical UTF-8/LF byte representation of a report."""
    return (
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def evaluate(document: dict[str, Any]) -> dict[str, Any]:
    """Validate matched evidence and produce a deterministic ablation report."""
    schema_version = document.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        raise AblationError(f"schema_version must be {SCHEMA_VERSION}")

    dataset_manifest_sha256 = _require_sha256(
        _require_text(document, "dataset_manifest_sha256"), "dataset_manifest_sha256"
    )
    split_id = _require_text(document, "split_id")
    mask_id = _require_text(document, "mask_id")
    variants = document.get("variants")
    if not isinstance(variants, list) or not variants:
        raise AblationError("variants must be a non-empty list")

    expected_samples: tuple[str, ...] | None = None
    seen_ids: set[str] = set()
    evaluated: list[dict[str, Any]] = []
    full_models: list[str] = []
    kinds_seen: set[str] = set()

    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            raise AblationError(f"variants[{index}] must be an object")
        variant_id = _require_text(variant, "variant_id")
        if variant_id in seen_ids:
            raise AblationError(f"duplicate variant_id: {variant_id}")
        seen_ids.add(variant_id)

        kind = variant.get("kind")
        if kind not in KINDS:
            raise AblationError(f"variant {variant_id} has unsupported kind: {kind!r}")
        kinds_seen.add(kind)

        sample_ids = variant.get("sample_ids")
        if not isinstance(sample_ids, list) or not sample_ids or not all(
            isinstance(sample_id, str) and sample_id for sample_id in sample_ids
        ):
            raise AblationError(f"variant {variant_id} sample_ids must be non-empty strings")
        if len(set(sample_ids)) != len(sample_ids):
            raise AblationError(f"variant {variant_id} contains duplicate sample_ids")
        sample_tuple = tuple(sample_ids)
        if expected_samples is None:
            expected_samples = sample_tuple
        elif sample_tuple != expected_samples:
            raise AblationError(
                f"variant {variant_id} does not use the exact ordered matched sample set"
            )

        raw_errors = variant.get("errors_m")
        if not isinstance(raw_errors, list):
            raise AblationError(f"{variant_id}.errors_m must be a list")
        errors = _finite_nonnegative(raw_errors, f"{variant_id}.errors_m")
        if len(errors) != len(sample_ids):
            raise AblationError(f"variant {variant_id} errors_m length does not match sample_ids")

        omitted = variant.get("omitted_features", [])
        if not isinstance(omitted, list) or not all(isinstance(name, str) and name for name in omitted):
            raise AblationError(f"variant {variant_id} omitted_features must contain strings")
        if kind == "feature_ablation" and not omitted:
            raise AblationError(f"feature ablation {variant_id} must omit at least one feature")
        if kind != "feature_ablation" and omitted:
            raise AblationError(f"only feature_ablation variants may declare omitted_features")
        if kind == "model":
            full_models.append(variant_id)

        evidence_sha256 = _require_sha256(
            _require_text(variant, "evidence_sha256"), f"{variant_id}.evidence_sha256"
        )

        evaluated.append(
            {
                "variant_id": variant_id,
                "kind": kind,
                "evidence_sha256": evidence_sha256,
                "omitted_features": sorted(omitted),
                "metrics": summarize(errors),
            }
        )

    missing = KINDS - kinds_seen
    if missing:
        raise AblationError("missing required variant kinds: " + ", ".join(sorted(missing)))
    if len(full_models) != 1:
        raise AblationError("exactly one full model variant is required")

    by_id = {variant["variant_id"]: variant for variant in evaluated}
    full_model = by_id[full_models[0]]
    baselines = [variant for variant in evaluated if variant["kind"] == "baseline"]
    best_baseline = min(baselines, key=lambda variant: (variant["metrics"]["rmse_m"], variant["variant_id"]))

    for variant in evaluated:
        metrics = variant["metrics"]
        variant["delta_vs_best_baseline_rmse_m"] = metrics["rmse_m"] - best_baseline["metrics"]["rmse_m"]
        if variant["kind"] == "feature_ablation":
            variant["delta_vs_full_model_rmse_m"] = metrics["rmse_m"] - full_model["metrics"]["rmse_m"]

    input_digest = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "scientific_status": "exploratory-not-promoted",
        "input_sha256": input_digest,
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "split_id": split_id,
        "mask_id": mask_id,
        "sample_count": len(expected_samples or ()),
        "best_baseline_variant_id": best_baseline["variant_id"],
        "full_model_variant_id": full_model["variant_id"],
        "variants": sorted(evaluated, key=lambda variant: variant["variant_id"]),
        "limitations": [
            "This report compares supplied matched error traces; it does not validate upstream model training.",
            "Results are exploratory and are not a model-promotion or safety claim.",
            "Raw private data and per-sample coordinates must remain outside Git.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    report = evaluate(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encode_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
