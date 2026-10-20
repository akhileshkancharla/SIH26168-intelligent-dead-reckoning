"""Fail-closed ONNX export workflow for WP-12.1.

This module deliberately contains no model and performs no training.  It exports
only an explicitly supplied, promotion-approved candidate and records an I-19
compatible manifest.  The current WP-11.5 publication is `do-not-promote`, so
using that publication exits before importing model code or writing artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = 1
EXPORTER_VERSION = "wp12.1-v1"
ALLOWED_DTYPES = {"float32", "float64", "int32", "int64", "bool"}


class ExportBlocked(RuntimeError):
    """Raised when the evidence is not eligible for model export."""


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
    if evidence_class in {"synthetic", "synthetic-fixture"}:
        raise ExportBlocked("synthetic evidence cannot authorize candidate export")
    if _text(document, "candidate_id") != candidate_id:
        raise ExportBlocked("promotion candidate_id does not match the candidate")


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
    seen: set[str] = set()
    validated_inputs: list[dict[str, Any]] = []
    for index, item in enumerate(inputs):
        if not isinstance(item, dict):
            raise ExportBlocked(f"inputs[{index}] must be an object")
        name = _text(item, "name")
        if name in seen:
            raise ExportBlocked(f"duplicate input name: {name}")
        seen.add(name)
        dtype = _text(item, "dtype")
        if dtype not in ALLOWED_DTYPES:
            raise ExportBlocked(f"unsupported dtype for {name}: {dtype}")
        shape = item.get("shape")
        if (
            not isinstance(shape, list)
            or not shape
            or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in shape)
        ):
            raise ExportBlocked(f"input {name} shape must contain positive integers")
        validated_inputs.append({"name": name, "dtype": dtype, "shape": shape})

    outputs = document.get("outputs")
    if (
        not isinstance(outputs, list)
        or not outputs
        or not all(isinstance(name, str) and name.strip() for name in outputs)
        or len(set(outputs)) != len(outputs)
    ):
        raise ExportBlocked("outputs must contain unique non-empty strings")

    required_manifest_fields = (
        "runtime_min",
        "input_contract",
        "window",
        "normalization",
        "outputs",
        "bounds",
        "training_run",
        "dataset_manifest",
        "metrics",
        "redistribution_status",
    )
    for field in required_manifest_fields:
        if field not in document:
            raise ExportBlocked(f"candidate is missing I-19 field: {field}")

    metrics = document["metrics"]
    if not isinstance(metrics, dict) or not metrics:
        raise ExportBlocked("metrics must be a non-empty object")
    for name, value in metrics.items():
        if (
            not isinstance(name, str)
            or not name.strip()
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ExportBlocked("metrics must map non-empty names to finite numbers")

    return {
        "candidate_id": candidate_id,
        "model_factory": model_factory,
        "state_dict": state_dict,
        "opset": opset,
        "inputs": validated_inputs,
        "output_names": [name.strip() for name in outputs],
    }


def _load_factory(reference: str) -> Callable[[], Any]:
    if ":" not in reference:
        raise ExportBlocked("model_factory must use 'module.path:callable'")
    module_name, callable_name = reference.rsplit(":", 1)
    try:
        factory = getattr(importlib.import_module(module_name), callable_name)
    except (ImportError, AttributeError) as error:
        raise ExportBlocked(f"cannot import model_factory {reference}: {error}") from error
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
    validate_promotion(load_json(promotion_path), candidate["candidate_id"])

    output_directory.mkdir(parents=True, exist_ok=True)
    model_path = output_directory / "model.onnx"
    manifest_path = output_directory / "model_manifest.json"
    if model_path.exists() or manifest_path.exists():
        raise ExportBlocked("refusing to overwrite an existing model bundle")

    try:
        import torch
        import onnx
    except ImportError as error:
        raise ExportBlocked(
            "export requires pinned torch and onnx packages in the approved private workspace"
        ) from error

    dtype_map = {
        "float32": torch.float32,
        "float64": torch.float64,
        "int32": torch.int32,
        "int64": torch.int64,
        "bool": torch.bool,
    }
    weights_path = (candidate_path.parent / candidate["state_dict"]).resolve()
    if not weights_path.is_file():
        raise ExportBlocked(f"state_dict does not exist: {weights_path}")

    model = _load_factory(candidate["model_factory"])()
    try:
        state = torch.load(weights_path, map_location="cpu", weights_only=True)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state, strict=True)
    except Exception as error:
        raise ExportBlocked(f"candidate weights cannot be loaded strictly: {error}") from error
    model.eval()

    tensors = [
        torch.zeros(tuple(item["shape"]), dtype=dtype_map[item["dtype"]])
        for item in candidate["inputs"]
    ]
    arguments: Any = tensors[0] if len(tensors) == 1 else tuple(tensors)
    try:
        with torch.no_grad():
            torch.onnx.export(
                model,
                arguments,
                model_path,
                export_params=True,
                do_constant_folding=True,
                input_names=[item["name"] for item in candidate["inputs"]],
                output_names=candidate["output_names"],
                opset_version=candidate["opset"],
            )
        onnx_model = onnx.load(str(model_path))
        onnx.checker.check_model(onnx_model)
    except Exception as error:
        model_path.unlink(missing_ok=True)
        raise ExportBlocked(f"ONNX export or validation failed: {error}") from error

    model_hash = _sha256(model_path)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "model_id": candidate["candidate_id"],
        "sha256": model_hash,
        "format": "onnx",
        "opset": candidate["opset"],
        "runtime_min": candidate_document["runtime_min"],
        "input_contract": candidate_document["input_contract"],
        "window": candidate_document["window"],
        "normalization": candidate_document["normalization"],
        "outputs": candidate_document["outputs"],
        "bounds": candidate_document["bounds"],
        "training_run": candidate_document["training_run"],
        "dataset_manifest": candidate_document["dataset_manifest"],
        "metrics": candidate_document["metrics"],
        "redistribution_status": candidate_document["redistribution_status"],
        "exporter_version": EXPORTER_VERSION,
        "candidate_descriptor_sha256": _sha256(candidate_path),
        "promotion_evidence_sha256": _sha256(promotion_path),
    }
    manifest_path.write_bytes(_canonical_bytes(manifest))
    return model_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--promotion", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    try:
        model, manifest = export_candidate(
            args.candidate.resolve(),
            args.promotion.resolve(),
            args.output_directory.resolve(),
        )
    except ExportBlocked as error:
        raise SystemExit(f"BLOCKED: {error}") from error
    print(f"exported {model}")
    print(f"manifest {manifest}")


if __name__ == "__main__":
    main()
