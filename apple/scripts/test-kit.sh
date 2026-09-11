#!/usr/bin/env bash
set -euo pipefail

# Resolve directory of this script's parent (apple/) so it's runnable from anywhere.
APPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-$APPLE_DIR/.build/results}"
mkdir -p "$RESULTS_DIR"

echo "---- HDHROpenKit: swift test ----"
swift test --package-path "$APPLE_DIR/HDHROpenKit" --enable-code-coverage

echo "---- HDHROpenKit: coverage export ----"
KIT_XCTEST=$(find "$APPLE_DIR/HDHROpenKit/.build" -name "*.xctest" -not -path "*.dSYM*" | head -n 1)
if [ -z "$KIT_XCTEST" ]; then
    echo "error: no .xctest bundle found under HDHROpenKit/.build" >&2
    exit 1
fi
KIT_BINARY="$KIT_XCTEST/Contents/MacOS/$(basename "$KIT_XCTEST" .xctest)"
KIT_PROFDATA=$(find "$APPLE_DIR/HDHROpenKit/.build" -name "default.profdata" | head -n 1)
if [ -z "$KIT_PROFDATA" ]; then
    echo "error: no default.profdata found under HDHROpenKit/.build" >&2
    exit 1
fi
xcrun llvm-cov export "$KIT_BINARY" -instr-profile "$KIT_PROFDATA" \
    -ignore-filename-regex='\.build|Tests/' > "$RESULTS_DIR/kit_coverage.json"
