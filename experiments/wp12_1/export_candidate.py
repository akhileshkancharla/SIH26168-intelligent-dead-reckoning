"""Fail-closed ONNX export workflow for WP-12.1.

This module contains no model and performs no training. It exports only an
explicitly supplied, promotion-approved candidate and records an I-19-compatible
manifest. The current WP-11.5 publication is do-not-promote, so using that
publication exits before importing model code or writing artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable

SCHEMA_VERSION = 1
EXPORTER_VERSION = "wp12.1-v1"
ALLOWED_DTYPES = {"float32", "float64", "int32", "int64", "bool"}
APPROVED_REAL_EVIDENCE_CLASSES = frozenset(
    {
        "held-out-real-world",
        "real-world-field-validation",
    }
)


class ExportBlocked(RuntimeError):
    """Raised when evidence or candidate inputs are not eligible for export."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExportBlocked(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ExportBlocked(f"non-standard JSON constant: {value}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExportBlocked(f"cannot read canonical JSON {path}: {error}") from error
    if not isinstance(document, dict):
        raise ExportBlocked(f"{path} must contain one JSON object")
    return document


def _text(document: dict[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ExportBlocked(f"{field} must be a non-empty string")
    return value.strip()


def _integer(document: dict[str, Any], field: str) -> int:
    value = document.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExportBlocked(f"{field} must be an integer")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def validate_promotion(document: dict[str, Any], candidate_id: str) -> None:
    if _integer(document, "schema_version") != SCHEMA_VERSION:
        raise ExportBlocked("promotion schema_version must be 1")
    if document.get("recommendation") != "promote":
        raise ExportBlocked(
            "promotion recommendation is not 'promote'; no model may be exported"
        )
    if document.get("scientific_status") not in {
        "promotion-approved",
        "candidate-approved",
    }:
        raise ExportBlocked("promotion evidence is not candidate-approved")
    evidence_class = _text(document, "evidence_class")
    if evidence_class not in APPROVED_REAL_EVIDENCE_CLASSES:
        allowed = ", ".join(sorted(APPROVED_REAL_EVIDENCE_CLASSES))
        raise ExportBlocked(
            f"evidence_class is not approved real-world evidence; expected one of: {allowed}"
        )
    if _text(document, "candidate_id") != candidate_id:
        raise ExportBlocked("promotion candidate_id does not match the candidate")


def _validate_metrics(value: Any) -> dict[str, int | float]:
    if not isinstance(value, dict) or not value:
        raise ExportBlocked("metrics must be a non-empty object")
    validated: dict[str, int | float] = {}
    for name, metric in value.items():
        if (
            not isinstance(name, str)
            or not name.strip()
            or isinstance(metric, bool)
            or not isinstance(metric, (int, float))
            or not math.isfinite(metric)
        ):
            raise ExportBlocked("metrics must map non-empty names to finite numbers")
        validated[name.strip()] = metric
    if len(validated) != len(value):
        raise ExportBlocked("metric names must be unique after trimming")
    return validated


def validate_candidate(document: dict[str, Any]) -> dict[str, Any]:
    if _integer(document, "schema_version") != SCHEMA_VERSION:
        raise ExportBlocked("candidate schema_version must be 1")

    candidate_id = _text(document, "candidate_id")
    model_factory = _text(document, "model_factory")
    state_dict = _text(document, "state_dict")
    opset = _integer(document, "opset_version")
    if not 13 <= opset <= 21:
        raise ExportBlocked("opset_version must be between 13 and 21")

    inputs = document.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise ExportBlocked("inputs must be a non-empty list")
    seen_inputs: set[str] = set()
    validated_inputs: list[dict[str, Any]] = []
    for index, item in enumerate(inputs):
        if not isinstance(item, dict):
            raise ExportBlocked(f"inputs[{index}] must be an object")
        name = _text(item, "name")
        if name in seen_inputs:
            raise ExportBlocked(f"duplicate input name: {name}")
        seen_inputs.add(name)
        dtype = _text(item, "dtype")
        if dtype not in ALLOWED_DTYPES:
            raise ExportBlocked(f"unsupported dtype for {name}: {dtype}")
        shape = item.get("shape")
        if (
            not isinstance(shape, list)
            or not shape
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
                for value in shape
            )
        ):
            raise ExportBlocked(
                f"input {name} shape must contain positive integers"
            )
        validated_inputs.append({"name": name, "dtype": dtype, "shape": shape})

    outputs = document.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ExportBlocked("outputs must be a non-empty list")
    normalized_outputs: list[str] = []
    for value in outputs:
        if not isinstance(value, str) or not value.strip():
            raise ExportBlocked("outputs must contain non-empty strings")
        normalized_outputs.append(value.strip())
    if len(set(normalized_outputs)) != len(normalized_outputs):
        raise ExportBlocked("outputs must be unique after trimming")

    validated = {
        "candidate_id": candidate_id,
        "model_factory": model_factory,
        "state_dict": state_dict,
        "opset": opset,
        "inputs": validated_inputs,
        "output_names": normalized_outputs,
        "runtime_min": _text(document, "runtime_min"),
        "input_contract": _text(document, "input_contract"),
        "window": _text(document, "window"),
        "normalization": _text(document, "normalization"),
        "outputs": normalized_outputs,
        "bounds": _text(document, "bounds"),
        "training_run": _text(document, "training_run"),
        "dataset_manifest": _text(document, "dataset_manifest"),
        "metrics": _validate_metrics(document.get("metrics")),
        "redistribution_status": _text(document, "redistribution_status"),
    }
    return validated


def _load_factory(reference: str) -> Callable[[], Any]:
    if ":" not in reference:
        raise ExportBlocked("model_factory must use 'module.path:callable'")
    module_name, callable_name = reference.rsplit(":", 1)
    try:
        factory = getattr(importlib.import_module(module_name), callable_name)
    except (ImportError, AttributeError) as error:
        raise ExportBlocked(
            f"cannot import model_factory {reference}: {error}"
        ) from error
    if not callable(factory):
        raise ExportBlocked("model_factory target is not callable")
    return factory


def export_candidate(
    candidate_path: Path,
    promotion_path: Path,
    output_directory: Path,
) -> tuple[Path, Path]:
    candidate_document = load_json(candidate_path)
    candidate = validate_candidate(candidate_document)
    promotion_document = load_json(promotion_path)
    validate_promotion(promotion_document, candidate["candidate_id"])

    if output_directory.exists():
        raise ExportBlocked(
            f"refusing existing output directory: {output_directory}"
        )

    try:
        import torch
        import onnx
    except ImportError as error:
        raise ExportBlocked(
            "export requires pinned torch and onnx packages in the approved private workspace"
        ) from error

    weights_path = (candidate_path.parent / candidate["state_dict"]).resolve()
    if not weights_path.is_file():
        raise ExportBlocked(f"state_dict does not exist: {weights_path}")

    model = _load_factory(candidate["model_factory"])()
    try:
        state = torch.load(
            weights_path,
            map_location="cpu",
            weights_only=True,
        )
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state, strict=True)
    except Exception as error:
        raise ExportBlocked(
            f"candidate weights cannot be loaded strictly: {error}"
        ) from error
    model.eval()

    dtype_map = {
        "float32": torch.float32,
        "float64": torch.float64,
        "int32": torch.int32,
        "int64": torch.int64,
        "bool": torch.bool,
    }
    tensors = [
        torch.zeros(tuple(item["shape"]), dtype=dtype_map[item["dtype"]])
        for item in candidate["inputs"]
    ]
    arguments: Any = tensors[0] if len(tensors) == 1 else tuple(tensors)

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    staging_directory = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.staging-",
            dir=output_directory.parent,
        )
    )
    staged_model = staging_directory / "model.onnx"
    staged_manifest = staging_directory / "model_manifest.json"

    try:
        with torch.no_grad():
            torch.onnx.export(
                model,
                arguments,
                staged_model,
                export_params=True,
                do_constant_folding=True,
                input_names=[item["name"] for item in candidate["inputs"]],
                output_names=candidate["output_names"],
                opset_version=candidate["opset"],
            )
        onnx_model = onnx.load(str(staged_model))
        onnx.checker.check_model(onnx_model)

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "model_id": candidate["candidate_id"],
            "sha256": _sha256(staged_model),
            "format": "onnx",
            "opset": candidate["opset"],
            "runtime_min": candidate["runtime_min"],
            "input_contract": candidate["input_contract"],
            "window": candidate["window"],
            "normalization": candidate["normalization"],
            "outputs": candidate["outputs"],
            "bounds": candidate["bounds"],
            "training_run": candidate["training_run"],
            "dataset_manifest": candidate["dataset_manifest"],
            "metrics": candidate["metrics"],
            "redistribution_status": candidate["redistribution_status"],
            "exporter_version": EXPORTER_VERSION,
            "candidate_descriptor_sha256": _sha256(candidate_path),
            "promotion_evidence_sha256": _sha256(promotion_path),
        }
        staged_manifest.write_bytes(_canonical_bytes(manifest))
        staging_directory.replace(output_directory)
    except Exception as error:
        shutil.rmtree(staging_directory, ignore_errors=True)
        if isinstance(error, ExportBlocked):
            raise
        raise ExportBlocked(
            f"ONNX export, validation, or atomic publication failed: {error}"
        ) from error

    return (
        output_directory / "model.onnx",
        output_directory / "model_manifest.json",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--promotion", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        model, manifest = export_candidate(
            args.candidate.resolve(),
            args.promotion.resolve(),
            args.output_dir.resolve(),
        )
    except ExportBlocked as error:
        raise SystemExit(f"BLOCKED: {error}") from error
    print(f"exported {model}")
    print(f"manifest {manifest}")


if __name__ == "__main__":
    main()
