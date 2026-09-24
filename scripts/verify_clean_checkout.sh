#!/usr/bin/env bash
# Clean-checkout truth verifier (PRD v9 §26.10 / NFR-06).
#
# Verifies the COMMITTED HEAD in an ephemeral detached git worktree: locked
# environment, unit test selection, lint, type check and declared-artifact
# reproducibility (lockfile, SBOM). Working-tree state never influences the
# verdict. Engineering gate only: it never converts green checks into
# scientific validation.
#
# Usage:
#   scripts/verify_clean_checkout.sh [--report PATH]
#
# Environment:
#   NTRUTH_CLEAN_CHECKOUT_QUICK=1   restrict pytest to -k "schemas or rules or ingest"
#                                   (declared in the output; default runs the
#                                   whole tests/unit tree minus the performance
#                                   marker)

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
REPORT_PATH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --report)
      [[ $# -ge 2 ]] || { echo "--report requires a path" >&2; exit 2; }
      REPORT_PATH="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

HEAD_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
BRANCH_LABEL="$(git -C "$REPO_ROOT" branch --show-current || true)"
[[ -n "$BRANCH_LABEL" ]] || BRANCH_LABEL="(detached)"
case "$REPORT_PATH" in
  "") ;;
  /*) ;;
  *) REPORT_PATH="$PWD/$REPORT_PATH" ;;
esac
RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/ntruth-clean-checkout.XXXXXX")"
LOG_DIR="$RUN_DIR/logs"
WORKTREE="$RUN_DIR/worktree"
mkdir -p "$LOG_DIR"

OVERALL="PASS"
declare -a CHECK_NAMES=()
declare -a CHECK_RESULTS=()
declare -a CHECK_DETAILS=()

record() {
  local name="$1" result="$2" detail="$3"
  CHECK_NAMES+=("$name")
  CHECK_RESULTS+=("$result")
  CHECK_DETAILS+=("$detail")
  printf '%-4s %s %s\n' "$result" "$name" "$detail"
}

fail() {
  OVERALL="FAIL"
}

run_check() {
  local name="$1"
  shift
  local log="$LOG_DIR/$name.log"
  if "$@" >"$log" 2>&1; then
    record "$name" "PASS" "log: $log"
  else
    local status=$?
    record "$name" "FAIL" "exit=$status log: $log"
    fail
    tail -n 25 "$log" | sed 's/^/    | /' >&2 || true
  fi
}

cleanup() {
  if [[ "$OVERALL" == "PASS" ]]; then
    git -C "$REPO_ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
    rm -rf "$RUN_DIR"
  else
    echo "kept failing-run artifacts (worktree included) under: $RUN_DIR" >&2
  fi
}
trap cleanup EXIT

printf '# Clean-checkout verification of %s (%s)\n' "$HEAD_SHA" "$BRANCH_LABEL"

if git -C "$REPO_ROOT" worktree add --detach "$WORKTREE" "$HEAD_SHA" >"$LOG_DIR/worktree_add.log" 2>&1; then
  record "worktree_add" "PASS" "detached HEAD $HEAD_SHA at $WORKTREE"
else
  record "worktree_add" "FAIL" "could not create detached worktree"
  fail
  exit 1
fi

cd "$WORKTREE"

SYNC_VARIANT="--frozen"
if ! uv sync --frozen --extra dev --extra api >"$LOG_DIR/uv_sync.log" 2>&1; then
  if grep -qiE "unrecognized|unexpected argument|no such option" "$LOG_DIR/uv_sync.log"; then
    SYNC_VARIANT="--locked"
    if uv sync --locked --extra dev --extra api >>"$LOG_DIR/uv_sync.log" 2>&1; then
      record "uv_sync" "PASS" "variant: $SYNC_VARIANT (--frozen unsupported by $(uv --version))"
    else
      record "uv_sync" "FAIL" "variant: $SYNC_VARIANT"
      fail
    fi
  else
    record "uv_sync" "FAIL" "variant: $SYNC_VARIANT"
    fail
  fi
else
  record "uv_sync" "PASS" "variant: $SYNC_VARIANT --extra dev --extra api"
fi

if [[ "$OVERALL" == "PASS" ]]; then
  run_check "lock_up_to_date" uv lock --check

  if [[ "${NTRUTH_CLEAN_CHECKOUT_QUICK:-0}" == "1" ]]; then
    PYTEST_SELECTION='tests/unit -k "schemas or rules or ingest" (declared reduced scope)'
    run_check "pytest_unit" uv run pytest tests/unit -q -x --tb=no -m "not performance" -k "schemas or rules or ingest"
  else
    PYTEST_SELECTION='tests/unit -m "not performance" -x (full unit tree)'
    run_check "pytest_unit" uv run pytest tests/unit -q -x --tb=no -m "not performance"
  fi

  run_check "ruff_check_packages" uv run ruff check packages
  run_check "mypy_packages" uv run mypy packages

  if [[ -f scripts/generate_sbom.py && -f sbom.cdx.json ]]; then
    run_check "sbom_reproducible" uv run python scripts/generate_sbom.py --check sbom.cdx.json
  else
    record "sbom_reproducible" "SKIP" "scripts/generate_sbom.py or sbom.cdx.json absent"
  fi
else
  record "remaining_checks" "SKIP" "not run: environment setup failed"
fi

echo
echo "== Summary ($OVERALL) =="
for i in "${!CHECK_NAMES[@]}"; do
  printf '%-4s %s\n' "${CHECK_RESULTS[$i]}" "${CHECK_NAMES[$i]}"
done
echo "head: $HEAD_SHA"
echo "branch label: $BRANCH_LABEL"
echo "pytest selection: ${PYTEST_SELECTION:-n/a}"
echo "overall: $OVERALL"

if [[ -n "$REPORT_PATH" ]]; then
  {
    echo "# Clean-checkout verification report — $(date -u '+%Y-%m-%d %H:%M UTC')"
    echo
    echo "- **Head verified:** \`$HEAD_SHA\` (ephemeral detached worktree; working-tree files excluded by construction)"
    echo "- **Branch label at run time:** $BRANCH_LABEL"
    echo "- **Toolchain:** $(uv --version), $(python3 --version 2>/dev/null || echo 'python3 n/a')"
    echo "- **Pytest selection:** ${PYTEST_SELECTION:-n/a}"
    echo
    echo "| Check | Result | Detail |"
    echo "|---|---|---|"
    for i in "${!CHECK_NAMES[@]}"; do
      printf '| `%s` | %s | %s |\n' "${CHECK_NAMES[$i]}" "${CHECK_RESULTS[$i]}" "${CHECK_DETAILS[$i]}"
    done
    echo
    echo "**Overall:** $OVERALL"
    if [[ "$OVERALL" == "PASS" ]]; then
      echo
      echo "All enabled engineering checks passed from a virgin checkout of the verified commit."
      echo "This is a portability/reproducibility gate (PRD v9 §26.10, NFR-06); it is not scientific validation."
    else
      echo
      echo "Residual blockers above are real failures observed on this run; they are not waived or reinterpreted."
    fi
  } >"$REPORT_PATH"
  echo "report written: $REPORT_PATH"
fi

[[ "$OVERALL" == "PASS" ]]
