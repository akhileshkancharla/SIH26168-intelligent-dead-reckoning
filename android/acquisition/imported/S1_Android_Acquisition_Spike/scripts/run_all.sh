#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
./scripts/run_host_tests.sh
./gradlew --no-daemon test lint assembleDebug assembleDebugAndroidTest
PYTHONPATH="$project_root" python3 -m analyzer.s1_analyzer fixtures/deterministic_session --output results/fixture_analysis
