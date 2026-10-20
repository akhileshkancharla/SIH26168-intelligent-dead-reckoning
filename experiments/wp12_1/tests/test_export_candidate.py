from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "export_candidate.py"
SPEC = importlib.util.spec_from_file_location("wp12_1_export_candidate", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def candidate() -> dict[str, object]:
    return {
        "schema_version": 1,
        "candidate_id": "real-candidate",
        "model_factory": "private_model.factory:build",
        "state_dict": "candidate.pt",
        "opset_version": 17,
        "inputs": [
            {
                "name": "imu_window",
                "shape": [1, 100, 6],
                "dtype": "float32",
            }
        ],
        "outputs": ["displacement"],
        "runtime_min": "python-runtime-version",
        "input_contract": "six ordered IMU features in SI units",
        "window": "100 samples",
        "normalization": "training normalization identifier",
        "bounds": "documented output bounds",
        "training_run": "immutable-run-id",
        "dataset_manifest": "immutable-dataset-id",
        "metrics": {"held_out_rmse": 1.25},
        "redistribution_status": "private; approval required",
    }


def promotion(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 1,
        "recommendation": "promote",
        "scientific_status": "promotion-approved",
        "evidence_class": "held-out-real-world",
        "candidate_id": "real-candidate",
    }
    document.update(overrides)
    return document


class FakeModel:
    def __init__(self) -> None:
        self.loaded: tuple[object, bool] | None = None
        self.evaluation = False

    def load_state_dict(self, state: object, *, strict: bool) -> None:
        self.loaded = (state, strict)

    def eval(self) -> None:
        self.evaluation = True


class NoGrad:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None


def fake_modules(*, checker_error: Exception | None = None) -> tuple[dict[str, types.ModuleType], FakeModel]:
    model = FakeModel()
    factory_module = types.ModuleType("private_model.factory")
    factory_module.build = lambda: model

    torch = types.ModuleType("torch")
    torch.float32 = "float32"
    torch.float64 = "float64"
    torch.int32 = "int32"
    torch.int64 = "int64"
    torch.bool = "bool"
    torch.zeros = lambda shape, dtype: {"shape": shape, "dtype": dtype}
    torch.load = lambda *args, **kwargs: {"weight": "value"}
    torch.no_grad = lambda: NoGrad()

    onnx_api = types.SimpleNamespace()

    def write_onnx(
        model_arg: object,
        arguments: object,
        path: Path,
        **kwargs: object,
    ) -> None:
        self_contained = {
            "model": type(model_arg).__name__,
            "arguments": repr(arguments),
            "options": sorted(kwargs),
        }
        path.write_text(json.dumps(self_contained), encoding="utf-8")

    onnx_api.export = write_onnx
    torch.onnx = onnx_api

    onnx = types.ModuleType("onnx")
    onnx.load = lambda path: {"path": path}

    def check_model(model_arg: object) -> None:
        if checker_error is not None:
            raise checker_error

    onnx.checker = types.SimpleNamespace(check_model=check_model)
    return {
        "torch": torch,
        "onnx": onnx,
        "private_model.factory": factory_module,
    }, model


class CandidateValidationTests(unittest.TestCase):
    def test_accepts_complete_descriptor(self) -> None:
        validated = exporter.validate_candidate(candidate())
        self.assertEqual(validated["opset"], 17)
        self.assertEqual(validated["output_names"], ["displacement"])

    def test_rejects_non_finite_metric_before_export(self) -> None:
        document = candidate()
        document["metrics"] = {"held_out_rmse": float("nan")}
        with self.assertRaisesRegex(exporter.ExportBlocked, "finite numbers"):
            exporter.validate_candidate(document)

    def test_rejects_duplicate_input_names(self) -> None:
        document = candidate()
        document["inputs"] = [
            {"name": "imu_window", "shape": [1, 100, 6], "dtype": "float32"},
            {"name": "imu_window", "shape": [1, 100, 6], "dtype": "float32"},
        ]
        with self.assertRaisesRegex(exporter.ExportBlocked, "duplicate input"):
            exporter.validate_candidate(document)

    def test_rejects_output_names_that_collide_after_trimming(self) -> None:
        document = candidate()
        document["outputs"] = ["output", " output "]
        with self.assertRaisesRegex(exporter.ExportBlocked, "after trimming"):
            exporter.validate_candidate(document)

    def test_rejects_malformed_i19_fields(self) -> None:
        fields = (
            "runtime_min",
            "input_contract",
            "window",
            "normalization",
            "bounds",
            "training_run",
            "dataset_manifest",
            "redistribution_status",
        )
        for field in fields:
            with self.subTest(field=field):
                document = candidate()
                document[field] = None
                with self.assertRaisesRegex(exporter.ExportBlocked, field):
                    exporter.validate_candidate(document)

    def test_rejects_empty_or_malformed_metrics(self) -> None:
        for value in (None, {}, {"metric": True}, {"metric": "1.0"}):
            with self.subTest(value=value):
                document = candidate()
                document["metrics"] = value
                with self.assertRaisesRegex(exporter.ExportBlocked, "metrics"):
                    exporter.validate_candidate(document)


class PromotionGateTests(unittest.TestCase):
    def test_rejects_do_not_promote(self) -> None:
        with self.assertRaisesRegex(exporter.ExportBlocked, "not 'promote'"):
            exporter.validate_promotion(
                promotion(recommendation="do-not-promote"),
                "real-candidate",
            )

    def test_rejects_every_non_allowlisted_evidence_class(self) -> None:
        for evidence_class in (
            "synthetic",
            "synthetic-fixture",
            "synthetic-derived",
            "exploratory",
            "real-ish",
        ):
            with self.subTest(evidence_class=evidence_class):
                with self.assertRaisesRegex(
                    exporter.ExportBlocked,
                    "not approved real-world evidence",
                ):
                    exporter.validate_promotion(
                        promotion(evidence_class=evidence_class),
                        "real-candidate",
                    )

    def test_requires_explicit_evidence_class(self) -> None:
        document = promotion()
        del document["evidence_class"]
        with self.assertRaisesRegex(exporter.ExportBlocked, "evidence_class"):
            exporter.validate_promotion(document, "real-candidate")

    def test_accepts_each_allowlisted_real_evidence_class(self) -> None:
        for evidence_class in exporter.APPROVED_REAL_EVIDENCE_CLASSES:
            with self.subTest(evidence_class=evidence_class):
                exporter.validate_promotion(
                    promotion(evidence_class=evidence_class),
                    "real-candidate",
                )

    def test_rejects_candidate_mismatch(self) -> None:
        with self.assertRaisesRegex(exporter.ExportBlocked, "does not match"):
            exporter.validate_promotion(
                promotion(candidate_id="different"),
                "real-candidate",
            )

    def test_current_blocked_state_writes_no_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path = root / "candidate.json"
            promotion_path = root / "promotion.json"
            output = root / "bundle"
            candidate_path.write_text(json.dumps(candidate()), encoding="utf-8")
            promotion_path.write_text(
                json.dumps(
                    promotion(
                        recommendation="do-not-promote",
                        scientific_status="exploratory-only",
                        evidence_class="synthetic-fixture",
                    )
                ),
                encoding="utf-8",
            )
            with self.assertRaises(exporter.ExportBlocked):
                exporter.export_candidate(candidate_path, promotion_path, output)
            self.assertFalse(output.exists())


class AtomicExportTests(unittest.TestCase):
    def _write_inputs(self, root: Path) -> tuple[Path, Path]:
        candidate_path = root / "candidate.json"
        promotion_path = root / "promotion.json"
        candidate_path.write_text(json.dumps(candidate()), encoding="utf-8")
        promotion_path.write_text(json.dumps(promotion()), encoding="utf-8")
        (root / "candidate.pt").write_bytes(b"private-test-weights")
        return candidate_path, promotion_path

    def test_refuses_any_existing_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path, promotion_path = self._write_inputs(root)
            output = root / "bundle"
            output.mkdir()
            with self.assertRaisesRegex(
                exporter.ExportBlocked,
                "existing output directory",
            ):
                exporter.export_candidate(
                    candidate_path,
                    promotion_path,
                    output,
                )
            self.assertEqual(list(output.iterdir()), [])

    def test_checker_failure_leaves_no_bundle_or_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path, promotion_path = self._write_inputs(root)
            output = root / "bundle"
            modules, _ = fake_modules(checker_error=ValueError("invalid graph"))
            with mock.patch.dict(sys.modules, modules):
                with self.assertRaisesRegex(
                    exporter.ExportBlocked,
                    "atomic publication failed",
                ):
                    exporter.export_candidate(
                        candidate_path,
                        promotion_path,
                        output,
                    )
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".bundle.staging-*")), [])

    def test_success_publishes_complete_model_and_manifest_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_path, promotion_path = self._write_inputs(root)
            output = root / "bundle"
            modules, model = fake_modules()
            with mock.patch.dict(sys.modules, modules):
                model_path, manifest_path = exporter.export_candidate(
                    candidate_path,
                    promotion_path,
                    output,
                )

            self.assertEqual(model_path, output / "model.onnx")
            self.assertEqual(manifest_path, output / "model_manifest.json")
            self.assertTrue(model.evaluation)
            self.assertEqual(model.loaded, ({"weight": "value"}, True))
            self.assertEqual(
                set(path.name for path in output.iterdir()),
                {"model.onnx", "model_manifest.json"},
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["model_id"], "real-candidate")
            self.assertEqual(manifest["outputs"], ["displacement"])
            self.assertEqual(
                manifest["sha256"],
                hashlib.sha256(model_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                manifest["candidate_descriptor_sha256"],
                hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                manifest["promotion_evidence_sha256"],
                hashlib.sha256(promotion_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(list(root.glob(".bundle.staging-*")), [])


class JsonBoundaryTests(unittest.TestCase):
    def test_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text(
                '{"schema_version": 1, "schema_version": 1}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(exporter.ExportBlocked, "duplicate JSON key"):
                exporter.load_json(path)


if __name__ == "__main__":
    unittest.main()
