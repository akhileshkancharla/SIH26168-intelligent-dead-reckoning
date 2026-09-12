"""Exercise preflight finalization under the GitHub runner's PowerShell wrapper."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell")
RUNNER_SUFFIX = r"if ((Test-Path -LiteralPath variable:\LASTEXITCODE)) { exit $LASTEXITCODE }"


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Windows PowerShell is required")
class RunnerPreflightExitTest(unittest.TestCase):
    def run_finalization(self, failure_count: int) -> subprocess.CompletedProcess[str]:
        source = (ROOT / "ci/self_hosted_runner_preflight.ps1").read_text(encoding="utf-8")
        # Run the actual final decision without requiring the runner service
        # identity or all of the laptop's build tools in this regression test.
        decision = source[source.rindex("if ($failures.Count -gt 0)"):]
        python = sys.executable.replace("'", "''")
        script = "\n".join([
            'Set-StrictMode -Version Latest',
            '$ErrorActionPreference = "Stop"',
            '$failures = [System.Collections.Generic.List[string]]::new()',
            *['$failures.Add("synthetic prerequisite failure")'] * failure_count,
            f"& '{python}' -c 'raise SystemExit(23)'",
            'if ($LASTEXITCODE -ne 23) { throw "Failed to seed native exit code" }',
            decision,
            # ScriptHandlerHelpers.FixUpScriptContents appends this for
            # PowerShell steps, including custom PowerShell shell commands.
            RUNNER_SUFFIX,
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runner-preflight-finalization.ps1"
            path.write_text(script, encoding="utf-8")
            return subprocess.run(
                [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(path)],
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )

    def test_success_clears_a_previous_native_failure(self):
        result = self.run_finalization(failure_count=0)
        self.assertIn("PASS: Windows self-hosted runner preflight", result.stdout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_prerequisite_failure_still_exits_one(self):
        result = self.run_finalization(failure_count=1)
        self.assertIn("Preflight failed with 1 required prerequisite error(s).", result.stdout)
        self.assertNotIn("PASS:", result.stdout)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
