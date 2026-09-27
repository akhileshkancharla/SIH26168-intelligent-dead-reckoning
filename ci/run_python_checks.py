#!/usr/bin/env python3
"""Run a test group in a unique, clean environment outside the checkout."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", choices=("dataset", "python"))
    args = parser.parse_args()
    test_directories = (
        ("tools/dataset/tests",)
        if args.group == "dataset"
        else ("tools/bootstrap/tests", "tools/training/tests")
    )
    with tempfile.TemporaryDirectory(prefix=f"sih-ci-{args.group}-") as directory:
        location = Path(directory).resolve()
        if location.is_relative_to(ROOT):
            raise SystemExit("CI temporary environments must be outside the repository")
        venv.EnvBuilder(with_pip=True).create(location)
        python = location / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        # Pip's download cache is reusable; installed packages are always fresh.
        subprocess.run([str(python), "-m", "pip", "install", "-e", "."], cwd=ROOT, check=True)
        for tests in test_directories:
            subprocess.run(
                [str(python), "-m", "unittest", "discover", "-s", tests, "-v"],
                cwd=ROOT,
                check=True,
            )


if __name__ == "__main__":
    main()
