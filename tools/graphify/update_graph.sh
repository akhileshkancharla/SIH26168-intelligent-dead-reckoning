#!/usr/bin/env bash
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(CDPATH= cd -- "${script_dir}/../.." && pwd)"
expected_repository="akhileshkancharla/SIH26168-intelligent-dead-reckoning"
graphify_bin="${GRAPHIFY_BIN:-graphify}"
python_bin="${PYTHON_BIN:-python3}"

cd "${repo_root}"

git_root="$(git rev-parse --show-toplevel)"
if [[ "$(CDPATH= cd -- "${git_root}" && pwd)" != "${repo_root}" ]]; then
  echo "ERROR: script is not running in the expected repository root" >&2
  exit 1
fi

origin="$(git remote get-url origin)"
case "${origin}" in
  *github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning|*github.com/akhileshkancharla/SIH26168-intelligent-dead-reckoning.git|*github.com:akhileshkancharla/SIH26168-intelligent-dead-reckoning|*github.com:akhileshkancharla/SIH26168-intelligent-dead-reckoning.git) ;;
  *) echo "ERROR: origin does not match ${expected_repository}" >&2; exit 1 ;;
esac

command -v "${graphify_bin}" >/dev/null 2>&1 || { echo "ERROR: Graphify is unavailable" >&2; exit 1; }
command -v "${python_bin}" >/dev/null 2>&1 || { echo "ERROR: Python is unavailable" >&2; exit 1; }

installed_version=""
if installed_version="$(${python_bin} -c "import importlib.metadata as m; print(m.version('graphifyy'))" 2>/dev/null)"; then
  :
elif command -v uv >/dev/null 2>&1; then
  installed_version="$(uv tool list | awk '/^graphifyy[[:space:]]+v?[0-9]+\.[0-9]+\.[0-9]+/ {sub(/^v/, "", $2); print $2; exit}')"
fi
if [[ -z "${installed_version}" ]]; then
  echo "ERROR: unable to identify the installed Graphify package version exactly" >&2
  exit 1
fi

configured_version="$(${python_bin} -c "import json; print(json.load(open('tools/graphify/graphify_config.json', encoding='utf-8'))['graphify_version'])")"
if [[ "${installed_version}" != "${configured_version}" ]]; then
  echo "ERROR: Graphify version mismatch: configured ${configured_version}, installed ${installed_version}" >&2
  exit 1
fi

source_branch="$(git branch --show-current)"
source_parent_commit="$(git rev-parse HEAD)"
source_state="clean"
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  source_state="working-tree"
fi

echo "Graphify ${installed_version}; source ${source_branch} at ${source_parent_commit} (${source_state})"
if [[ -f graphify-out/graph.json ]]; then
  "${graphify_bin}" update .
else
  "${graphify_bin}" extract . --code-only
fi
"${graphify_bin}" cluster-only . --no-label
"${python_bin}" tools/graphify/sanitize_graph.py \
  --graphify-version "${installed_version}" \
  --source-branch "${source_branch}" \
  --source-parent-commit "${source_parent_commit}" \
  --source-state "${source_state}"
"${python_bin}" tools/graphify/verify_graph.py

"${python_bin}" -c "import json; m=json.load(open('docs/architecture/dependency-graph/metadata.json', encoding='utf-8')); print(f\"Snapshot verified: {m['node_count']} nodes, {m['edge_count']} edges, {m['community_count']} communities.\")"
git status --short -- .gitignore .graphifyignore AGENTS.md .github/workflows/graphify-check.yml ci docs tools/graphify
