#!/usr/bin/env bash
set -euo pipefail

# Resolve directory of this script (apple/) so it's runnable from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export RESULTS_DIR="$SCRIPT_DIR/.build/results"
rm -rf "$RESULTS_DIR"
mkdir -p "$RESULTS_DIR"

fail() {
    echo "=========================================================="
    echo " FAILED at stage: $1"
    echo "=========================================================="
    exit 1
}

echo "=========================================================="
echo " Running Apple Quality Checks (Lint, Format, Tests, Coverage) "
echo "=========================================================="

bash "$SCRIPT_DIR/scripts/lint.sh" || fail "Lint"
bash "$SCRIPT_DIR/scripts/test-kit.sh" || fail "HDHROpenKit swift test"
bash "$SCRIPT_DIR/scripts/test-app.sh" ios || fail "HDHROpeniOS xcodebuild test"
bash "$SCRIPT_DIR/scripts/test-app.sh" tv || fail "HDHROpenTV xcodebuild test"

echo "---- Combined + per-file coverage gate ----"
python3 "$SCRIPT_DIR/scripts/compute_coverage.py" \
    --kit-json "$RESULTS_DIR/kit_coverage.json" \
    --ios-json "$RESULTS_DIR/ios_coverage.json" \
    --tv-json "$RESULTS_DIR/tv_coverage.json" \
    --threshold 83.0 \
    --min-file-coverage 40.0 \
    || fail "coverage threshold gate"

echo "=========================================================="
echo " All Apple quality checks passed successfully!            "
echo "=========================================================="
