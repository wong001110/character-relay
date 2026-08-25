#!/usr/bin/env bash
# Run the bounded Python mutation scope from a WSL-native disposable copy.
#
# mutmut creates a high volume of cache/test files.  Running that workload under
# /mnt/<drive> can stall on the Windows 9p client, so this script never creates
# its work directory there.  It intentionally copies uncommitted source and
# tests too; `git archive` would make a phase check test the wrong revision.

set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "run_mutmut_wsl.sh must run inside a WSL/Linux shell." >&2
  exit 2
fi

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cache_root="${XDG_CACHE_HOME:-"$HOME/.cache"}/echo-masque-mutmut"
mkdir -p "$cache_root"
workdir="$(mktemp -d "$cache_root/run.XXXXXXXX")"

case "$workdir" in
  "$cache_root"/run.*) ;;
  *)
    echo "Refusing to clean an unexpected mutation work directory." >&2
    exit 2
    ;;
esac
cleanup_workdir() {
  if [[ "${MUTMUT_KEEP_WORKDIR:-}" == "1" ]]; then
    echo "Preserving mutation work directory for inspection: $workdir" >&2
    return
  fi
  rm -rf -- "$workdir"
}
trap cleanup_workdir EXIT

tar \
  --exclude='.git' \
  --exclude='mutants' \
  --exclude='.mypy_cache' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='__pycache__' \
  -C "$repository_root" \
  -cf - pyproject.toml src tests \
  | tar -xf - -C "$workdir"

mutmut_command="${MUTMUT_COMMAND:-mutmut}"
if ! command -v "$mutmut_command" >/dev/null 2>&1; then
  cat >&2 <<'EOF'
mutmut is not available in this WSL environment.
Create/activate a WSL-native Python environment, install the project's dev
dependencies, then set MUTMUT_COMMAND to its native mutmut executable if needed.
EOF
  exit 2
fi

cd "$workdir"
export PYTHONPATH="$workdir/src${PYTHONPATH:+:$PYTHONPATH}"

set +e
"$mutmut_command" run "$@"
run_status=$?
"$mutmut_command" results
results_status=$?
"$mutmut_command" export-cicd-stats
stats_status=$?
set -e

if [[ $run_status -ne 0 ]]; then
  exit "$run_status"
fi
if [[ $results_status -ne 0 ]]; then
  exit "$results_status"
fi
exit "$stats_status"
