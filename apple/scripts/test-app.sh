#!/usr/bin/env bash
set -euo pipefail

# Resolve directory of this script's parent (apple/) so it's runnable from anywhere.
APPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-$APPLE_DIR/.build/results}"
mkdir -p "$RESULTS_DIR"

PLATFORM="${1:-}"
case "$PLATFORM" in
    ios)
        SCHEME=HDHROpeniOS
        DEST_PLATFORM=ios
        PREFER="iPhone 17 Pro"
        ;;
    tv)
        SCHEME=HDHROpenTV
        DEST_PLATFORM=tvos
        PREFER="Apple TV 4K (3rd generation)"
        ;;
    *)
        echo "usage: $(basename "$0") <ios|tv>" >&2
        exit 1
        ;;
esac

DERIVED_DATA_PATH="${DERIVED_DATA_PATH:-$APPLE_DIR/.build/DerivedData-$PLATFORM}"
XCRESULT_PATH="$RESULTS_DIR/${PLATFORM}_test_results.xcresult"
rm -rf "$XCRESULT_PATH"

echo "---- Resolving $PLATFORM simulator destination ----"
DESTINATION=$(python3 "$APPLE_DIR/scripts/resolve_destination.py" "$DEST_PLATFORM" --prefer "$PREFER")
echo "$PLATFORM destination: $DESTINATION"

echo "---- $SCHEME: xcodebuild test ----"
xcodebuild test \
    -project "$APPLE_DIR/HDHROpen.xcodeproj" \
    -scheme "$SCHEME" \
    -destination "$DESTINATION" \
    -enableCodeCoverage YES \
    -derivedDataPath "$DERIVED_DATA_PATH" \
    -resultBundlePath "$XCRESULT_PATH"

echo "---- Exporting $SCHEME coverage JSON ----"
xcrun xccov view --report --json "$XCRESULT_PATH" > "$RESULTS_DIR/${PLATFORM}_coverage.json"
