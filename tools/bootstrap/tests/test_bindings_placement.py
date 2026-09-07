"""WP-01.6 note: this file covers WP-01.5 (Issue #29) — proving the
deterministic contract bindings are actually placed into their consuming
source trees (C++, Android/Kotlin, Python), not just generated into
contracts/generated/. See contracts/INTERFACE_SCHEMA_PLAN.md section 6.
"""
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
        """Proves the placed package is genuinely installable and
        importable as `sih26168_contracts` via normal `import` machinery
        -- not just that the file parses when loaded through a hand-rolled
        importlib.util spec, which says nothing about whether
        pyproject.toml's package-dir mapping actually works. CI installs
        the project with `pip install -e .` before running tests (see
        .github/workflows/python.yml); locally, skip unless that has been
        done.
        """
        try:
            import sih26168_contracts.enums as enums_mod
            import sih26168_contracts.models as models_mod
        except ImportError:
            self.skipTest(
                "sih26168_contracts is not installed; run `pip install -e .` "
                "from the repository root (CI does this automatically) to "
                "exercise this test."
            )

        # Guard against a stale/shadowing install: the imported module must
        # actually resolve back to the placed source under test.
        resolved = Path(models_mod.__file__).resolve()
        expected = (self.python_contracts_dir / "models.py").resolve()
        self.assertEqual(
            resolved,
            expected,
            f"sih26168_contracts.models resolved to {resolved}, not the placed "
            f"package at {expected} -- is a stale install shadowing it?",
        )

        ts = models_mod.TimestampV1(epoch_ns=1, arrival_elapsed_realtime_ns=1, clock_id="CLOCK_BOOTTIME")
        prov = models_mod.ProvenanceV1(
            evidence_id="ev-001",
            session_id="sess-001",
            stream_id="stream-accel",
            provenance_type=enums_mod.ProvenanceTypeV1.LIVE_DEVICE,
        )
        # is_finite/is_valid are required fields with no schema default,
        # so the generated dataclass requires them explicitly rather than
        # silently defaulting to True.
        gate = models_mod.ValidityGateV1(is_finite=True, is_valid=True)
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
