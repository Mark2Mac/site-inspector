#!/usr/bin/env bash
# run_tests.sh — smoke test runner for Mac / Linux
# Usage:
#   bash run_tests.sh              # pytest only (fast)
#   SITE_URL=https://example.com bash run_tests.sh  # + live crawl smoke test
set -euo pipefail

PASS=0
FAIL=0

ok()   { echo "[PASS] $*"; ((PASS++)); }
fail() { echo "[FAIL] $*"; ((FAIL++)); }
sep()  { echo ""; echo "=== $* ==="; echo ""; }

# ---------------------------------------------------------------------------
sep "Unit + integration tests"
if python -m pytest tests/ -q; then
    ok "pytest"
else
    fail "pytest"
fi

# ---------------------------------------------------------------------------
sep "CLI smoke"

if python -m site_inspector --help > /dev/null 2>&1; then
    ok "--help"
else
    fail "--help"
fi

if python -m site_inspector --version > /dev/null 2>&1; then
    ok "--version"
else
    fail "--version"
fi

# ---------------------------------------------------------------------------
sep "Live crawl (optional)"

if [[ -n "${SITE_URL:-}" ]]; then
    TMPDIR_RUN=$(mktemp -d)
    if python -m site_inspector crawl "$SITE_URL" --max-pages 3 --out "$TMPDIR_RUN" > /dev/null 2>&1; then
        ok "crawl $SITE_URL"
    else
        fail "crawl $SITE_URL"
    fi
    rm -rf "$TMPDIR_RUN"
else
    echo "(Skipped — set SITE_URL to enable)"
fi

# ---------------------------------------------------------------------------
sep "Summary"
echo "Passed: $PASS  Failed: $FAIL"
[[ $FAIL -eq 0 ]]
