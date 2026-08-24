#!/usr/bin/env bash
# Run the backend API for local/manual testing (auto-reloads on file changes).
# Usage: ./scripts/dev.sh [port]   (default port 8811)
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PORT="${1:-8811}"

exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "$PORT"
