#!/usr/bin/env bash
# The single verification gate: pytest (no skips allowed) + frontend build + lint.
# Usage: ./scripts/check.sh   (from any directory)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== pytest"
PYTEST_LOG="$(mktemp)"
trap 'rm -f "$PYTEST_LOG"' EXIT
uv run pytest -q -rs 2>&1 | tee "$PYTEST_LOG"
# Last line looks like: "5 passed, 1 skipped, 2 warnings in 0.12s"
SUMMARY="$(grep -E '[0-9]+ (passed|failed|skipped|error)' "$PYTEST_LOG" | tail -n 1 || true)"
count() { echo "$SUMMARY" | grep -oE "[0-9]+ $1" | grep -oE '^[0-9]+' || echo 0; }
PASSED="$(count passed)"
SKIPPED="$(count skipped)"
if [ "$PASSED" -eq 0 ]; then
  echo "check.sh: FAIL: pytest ran 0 passing tests ($SUMMARY)" >&2
  exit 1
fi
if [ "$SKIPPED" -ne 0 ]; then
  echo "check.sh: FAIL: pytest skipped $SKIPPED test(s); the chain requires 0 skipped" >&2
  exit 1
fi

cd "$ROOT/frontend"
echo "== npm run build"
npm run build
echo "== npm run lint"
npm run lint

echo "check.sh: OK — pytest $PASSED passed, $SKIPPED skipped; build OK; lint OK"
