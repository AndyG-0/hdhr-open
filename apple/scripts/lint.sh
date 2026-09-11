#!/usr/bin/env bash
set -euo pipefail

# Resolve directory of this script's parent (apple/) so it's runnable from anywhere.
APPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "---- SwiftLint ----"
swiftlint lint --config "$APPLE_DIR/.swiftlint.yml" "$APPLE_DIR"

echo "---- SwiftFormat (lint-only) ----"
swiftformat --lint --config "$APPLE_DIR/.swiftformat" "$APPLE_DIR"
