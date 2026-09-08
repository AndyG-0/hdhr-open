#!/usr/bin/env bash
set -euo pipefail

# Resolve directory of this script (apple/) so it's runnable from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RESULTS_DIR="$SCRIPT_DIR/.build/results"
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

echo "---- SwiftLint ----"
swiftlint lint --config "$SCRIPT_DIR/.swiftlint.yml" "$SCRIPT_DIR" || fail "SwiftLint"

echo "---- SwiftFormat (lint-only) ----"
swiftformat --lint --config "$SCRIPT_DIR/.swiftformat" "$SCRIPT_DIR" || fail "SwiftFormat"

echo "---- HDHROpenKit: swift test ----"
swift test --package-path "$SCRIPT_DIR/HDHROpenKit" --enable-code-coverage || fail "HDHROpenKit swift test"

echo "---- HDHROpenKit: coverage export ----"
KIT_XCTEST=$(find "$SCRIPT_DIR/HDHROpenKit/.build" -name "*.xctest" -not -path "*.dSYM*" | head -n 1)
if [ -z "$KIT_XCTEST" ]; then
    fail "HDHROpenKit coverage export (no .xctest bundle found)"
fi
KIT_BINARY="$KIT_XCTEST/Contents/MacOS/$(basename "$KIT_XCTEST" .xctest)"
KIT_PROFDATA=$(find "$SCRIPT_DIR/HDHROpenKit/.build" -name "default.profdata" | head -n 1)
if [ -z "$KIT_PROFDATA" ]; then
    fail "HDHROpenKit coverage export (no default.profdata found)"
fi
xcrun llvm-cov export "$KIT_BINARY" -instr-profile "$KIT_PROFDATA" \
    -ignore-filename-regex='\.build|Tests/' > "$RESULTS_DIR/kit_coverage.json" \
    || fail "HDHROpenKit coverage export"

echo "---- Resolving simulator destinations ----"
IOS_DESTINATION=$(python3 "$SCRIPT_DIR/scripts/resolve_destination.py" ios --prefer "iPhone 17 Pro") \
    || fail "resolve iOS simulator destination"
TVOS_DESTINATION=$(python3 "$SCRIPT_DIR/scripts/resolve_destination.py" tvos --prefer "Apple TV 4K (3rd generation)") \
    || fail "resolve tvOS simulator destination"
echo "iOS destination: $IOS_DESTINATION"
echo "tvOS destination: $TVOS_DESTINATION"

echo "---- HDHROpeniOS: xcodebuild test ----"
xcodebuild test \
    -project "$SCRIPT_DIR/HDHROpen.xcodeproj" \
    -scheme HDHROpeniOS \
    -destination "$IOS_DESTINATION" \
    -enableCodeCoverage YES \
    -resultBundlePath "$RESULTS_DIR/ios_test_results.xcresult" \
    || fail "HDHROpeniOS xcodebuild test"

echo "---- HDHROpenTV: xcodebuild test ----"
xcodebuild test \
    -project "$SCRIPT_DIR/HDHROpen.xcodeproj" \
    -scheme HDHROpenTV \
    -destination "$TVOS_DESTINATION" \
    -enableCodeCoverage YES \
    -resultBundlePath "$RESULTS_DIR/tv_test_results.xcresult" \
    || fail "HDHROpenTV xcodebuild test"

echo "---- Exporting app-target coverage JSON ----"
xcrun xccov view --report --json "$RESULTS_DIR/ios_test_results.xcresult" > "$RESULTS_DIR/ios_coverage.json" \
    || fail "iOS coverage export"
xcrun xccov view --report --json "$RESULTS_DIR/tv_test_results.xcresult" > "$RESULTS_DIR/tv_coverage.json" \
    || fail "tvOS coverage export"

echo "---- Combined coverage gate (80% threshold) ----"
python3 "$SCRIPT_DIR/scripts/compute_coverage.py" \
    --kit-json "$RESULTS_DIR/kit_coverage.json" \
    --ios-json "$RESULTS_DIR/ios_coverage.json" \
    --tv-json "$RESULTS_DIR/tv_coverage.json" \
    --threshold 80.0 \
    || fail "coverage threshold gate"

echo "=========================================================="
echo " All Apple quality checks passed successfully!            "
echo "=========================================================="
