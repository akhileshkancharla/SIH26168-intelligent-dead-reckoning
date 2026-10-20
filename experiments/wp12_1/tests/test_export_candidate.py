from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


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
        "inputs": [{"name": "imu_window", "shape": [1, 100, 6], "dtype": "float32"}],
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


class PromotionGateTests(unittest.TestCase):
    def test_rejects_do_not_promote(self) -> None:
        with self.assertRaisesRegex(exporter.ExportBlocked, "not 'promote'"):
            exporter.validate_promotion(promotion(recommendation="do-not-promote"), "real-candidate")

    def test_rejects_synthetic_evidence(self) -> None:
        with self.assertRaisesRegex(exporter.ExportBlocked, "synthetic evidence"):
            exporter.validate_promotion(promotion(evidence_class="synthetic-fixture"), "real-candidate")

    def test_requires_explicit_evidence_class(self) -> None:
        document = promotion()
        del document["evidence_class"]
        with self.assertRaisesRegex(exporter.ExportBlocked, "evidence_class"):
            exporter.validate_promotion(document, "real-candidate")

    def test_rejects_candidate_mismatch(self) -> None:
        with self.assertRaisesRegex(exporter.ExportBlocked, "does not match"):
            exporter.validate_promotion(promotion(candidate_id="different"), "real-candidate")

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


class JsonBoundaryTests(unittest.TestCase):
    def test_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
            with self.assertRaisesRegex(exporter.ExportBlocked, "duplicate JSON key"):
                exporter.load_json(path)


if __name__ == "__main__":
    unittest.main()
