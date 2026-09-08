#!/usr/bin/env bash
set -euo pipefail

# Resolve directory of this script (android/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo " Running Android Quality Checks (Lint, Unit Tests, Build) "
echo "=========================================================="

./gradlew qualityCheck "$@"

echo "=========================================================="
echo " All Android quality checks passed successfully!         "
echo "=========================================================="
