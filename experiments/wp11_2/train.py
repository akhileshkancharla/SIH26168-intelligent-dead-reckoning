"""Command-line entry point for deterministic WP-11.2 training evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from pathlib import Path

from experiments.wp11_2.core import (
    DEFAULT_FEATURES,
    VERSION,
    Sample,
    TrainingConfig,
    fit,
    load,
    split_by_group,
)


def metrics(rows: list[Sample], weights: list[float]) -> dict[str, float]:
    errors = [
        weights[0]
        + sum(weight * value for weight, value in zip(weights[1:], row.features))
        - row.target
        for row in rows
    ]
    result = {
        "mae": sum(map(abs, errors)) / len(errors),
        "rmse": math.sqrt(sum(error * error for error in errors) / len(errors)),
    }
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("metrics are non-finite")
    return result


def _group_digest(group_id: str) -> str:
    return hashlib.sha256(group_id.encode("utf-8")).hexdigest()


def train(path: Path, config: TrainingConfig) -> dict:
    rows = load(path, config)
    train_rows, validation_rows, train_groups, validation_groups = split_by_group(
        rows, config.train_fraction
    )
    weights = fit(train_rows, config.ridge)
    return {
        "schema_version": 1,
        "pipeline_version": VERSION,
        "status": "exploratory-not-promoted",
        "input": {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rows": len(rows),
            "groups": len(train_groups) + len(validation_groups),
        },
        "split": {
            "method": "ordered-journey-group-holdout",
            "group_column": config.group_column,
            "time_column": config.time_column,
            "train_rows": len(train_rows),
            "validation_rows": len(validation_rows),
            "train_group_sha256": [_group_digest(group) for group in train_groups],
            "validation_group_sha256": [
                _group_digest(group) for group in validation_groups
            ],
        },
        "model": {
            "kind": "ridge_linear_regression",
            "features": list(config.features),
            "target": config.target,
            "ridge": config.ridge,
            "intercept": weights[0],
            "coefficients": weights[1:],
        },
        "metrics": {
            "train": metrics(train_rows, weights),
            "validation": metrics(validation_rows, weights),
        },
        "runtime": {
            "python": platform.python_version(),
            "numeric_policy": "stdlib-float64-pivoted-elimination-v1",
        },
        "limitations": [
            "Exploratory offline evidence only; not a promotion claim.",
            "Group holdout does not replace frozen WP-11.3 masking and evaluation.",
            "Feature-name checks do not replace provenance and leakage audits.",
            "Cannot overwrite navigation-core state.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--features", nargs="+", default=list(DEFAULT_FEATURES))
    parser.add_argument("--ridge", type=float, default=1e-6)
    parser.add_argument("--train-fraction", type=float, default=0.8)
    parser.add_argument("--group-column", default="session_id")
    parser.add_argument("--time-column", default="timestamp_ns")
    arguments = parser.parse_args()
    config = TrainingConfig(
        tuple(arguments.features),
        arguments.target,
        arguments.ridge,
        arguments.train_fraction,
        arguments.group_column,
        arguments.time_column,
    )
    result = train(arguments.input, config)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
