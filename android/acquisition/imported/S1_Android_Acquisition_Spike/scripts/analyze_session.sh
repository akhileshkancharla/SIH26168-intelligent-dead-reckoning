#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo "Usage: $0 SESSION_DIRECTORY_OR_ZIP OUTPUT_DIRECTORY" >&2
  exit 64
fi
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$project_root" python3 -m analyzer.s1_analyzer "$1" --output "$2"
