#!/usr/bin/env python3
"""Guard the accepted independence boundary between C++ and NumPy."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PYTHON_ORACLE = ROOT / "core/navigation/verification/python"
CPP_PRODUCTION = (
    ROOT / "core/navigation/src/navigation_core.cpp",
    ROOT / "core/navigation/src/navigation_api.cpp",
)
PROHIBITED_PYTHON_MODULES = {"ctypes", "cffi", "pybind11", "subprocess"}


class ParityIndependenceTest(unittest.TestCase):
    def test_oracle_does_not_import_cpp_bridge_or_process_launcher(self) -> None:
        for path in sorted(PYTHON_ORACLE.glob("*.py")):
            if path.name.startswith("test_"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".", 1)[0])
            self.assertFalse(
                imported & PROHIBITED_PYTHON_MODULES,
                f"{path.name} imports prohibited coupling modules: "
                f"{sorted(imported & PROHIBITED_PYTHON_MODULES)}",
            )

    def test_production_cpp_has_no_python_runtime_dependency(self) -> None:
        prohibited = ("python.h", "pybind", "numpy", "popen(", "system(")
        for path in CPP_PRODUCTION:
            source = path.read_text(encoding="utf-8").lower()
            for marker in prohibited:
                self.assertNotIn(marker, source, f"{path.name} contains {marker}")


if __name__ == "__main__":
    unittest.main()
