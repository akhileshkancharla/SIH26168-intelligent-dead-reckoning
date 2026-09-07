"""WP-01.6 note: this file covers WP-01.5 (Issue #29) — proving the
deterministic contract bindings are actually placed into their consuming
source trees (C++, Android/Kotlin, Python), not just generated into
contracts/generated/. See contracts/INTERFACE_SCHEMA_PLAN.md section 6.
"""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


class BindingsPlacementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[3]
        cls.ci_script = cls.root / "ci/generate_contract_bindings.py"
        cls.generated_dir = cls.root / "contracts/generated"
        cls.cpp_contracts_dir = cls.root / "core/include/sih26168/contracts"
        cls.android_contracts_dir = cls.root / "android/app/src/main/java/org/sih26168/contracts"
        cls.python_contracts_dir = cls.root / "tools/contracts/sih26168_contracts"

    def test_check_mode_passes_for_placed_bindings(self):
        # ci/generate_contract_bindings.py --check covers every path in
        # generate_all_bindings(), which includes the placed copies; a
        # green run here is itself proof the consuming-tree files are
        # present and drift-free.
        result = subprocess.run(
            [sys.executable, str(self.ci_script), "--check"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"Codegen check failed: {result.stderr}")

    def test_cpp_bindings_are_byte_identical_to_generated(self):
        for name in ("enums.hpp", "models.hpp"):
            generated = (self.generated_dir / "cpp" / name).read_bytes()
            placed = (self.cpp_contracts_dir / name).read_bytes()
            self.assertEqual(generated, placed, f"core/include/.../contracts/{name} drifted from contracts/generated/cpp/{name}")

    def test_kotlin_bindings_are_byte_identical_to_generated(self):
        pairs = (("Enums.kt", "enums"), ("Models.kt", "models"))
        for filename, subdir in pairs:
            generated = (self.generated_dir / "kotlin" / filename).read_bytes()
            placed = (self.android_contracts_dir / subdir / filename).read_bytes()
            self.assertEqual(generated, placed, f"android/.../contracts/{subdir}/{filename} drifted from contracts/generated/kotlin/{filename}")

    def test_python_bindings_are_byte_identical_to_generated(self):
        for name in ("__init__.py", "enums.py", "models.py"):
            generated = (self.generated_dir / "python" / name).read_bytes()
            placed = (self.python_contracts_dir / name).read_bytes()
            self.assertEqual(generated, placed, f"tools/contracts/sih26168_contracts/{name} drifted from contracts/generated/python/{name}")

    def test_placed_python_package_is_importable_and_roundtrips(self):
        # Load the *placed* package directly (not contracts/generated/),
        # proving it is a real, importable Python package on its own —
        # the actual integration point WP-01.5 is responsible for.
        enums_spec = importlib.util.spec_from_file_location(
            "sih26168_contracts.enums", self.python_contracts_dir / "enums.py"
        )
        enums_mod = importlib.util.module_from_spec(enums_spec)
        sys.modules["sih26168_contracts.enums"] = enums_mod
        enums_spec.loader.exec_module(enums_mod)

        models_spec = importlib.util.spec_from_file_location(
            "sih26168_contracts.models", self.python_contracts_dir / "models.py"
        )
        models_mod = importlib.util.module_from_spec(models_spec)
        sys.modules["sih26168_contracts.models"] = models_mod
        models_spec.loader.exec_module(models_mod)

        ts = models_mod.TimestampV1(epoch_ns=1, arrival_elapsed_realtime_ns=1, clock_id="CLOCK_BOOTTIME")
        prov = models_mod.ProvenanceV1(
            evidence_id="ev-001",
            session_id="sess-001",
            stream_id="stream-accel",
            provenance_type=enums_mod.ProvenanceTypeV1.LIVE_DEVICE,
        )
        gate = models_mod.ValidityGateV1()
        env = models_mod.EvidenceEnvelopeV1(
            payload_type="RawSensorSample",
            timestamp=ts,
            provenance=prov,
            payload={"values": [0.1, 0.2, 9.8]},
            validity_gate=gate,
        )
        self.assertEqual(models_mod.EvidenceEnvelopeV1.from_dict(env.to_dict()), env)


if __name__ == "__main__":
    unittest.main()
