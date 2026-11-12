#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
PYTHONPATH="$project_root" python3 -m unittest discover -s tests -p 'test_*.py' -v
