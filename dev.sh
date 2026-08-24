#!/usr/bin/env bash
# Run backend (FastAPI, hot reload) and frontend (Vite dev server) together.
# Ports default to an offset from the stock 8000/5173 dev ports so this can
# run alongside another local project using the defaults.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$ROOT_DIR/backend/.env" ]; then
	echo "backend/.env not found — copying from backend/.env.example" >&2
	cp "$ROOT_DIR/backend/.env.example" "$ROOT_DIR/backend/.env"
fi

if [ ! -f "$ROOT_DIR/frontend/.env" ]; then
	echo "frontend/.env not found — copying from frontend/.env.example" >&2
	cp "$ROOT_DIR/frontend/.env.example" "$ROOT_DIR/frontend/.env"
fi

cleanup() {
	trap - EXIT INT TERM
	jobs -p | xargs -r kill 2>/dev/null
	wait 2>/dev/null
}
trap cleanup EXIT INT TERM

HOST="${HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8100}"
FRONTEND_PORT="${FRONTEND_PORT:-5273}"

# The committed .env files default these to the Vite/uvicorn stock ports
# (5173/8000) — override so they track whichever ports this script actually
# starts on.
CORS_ORIGIN="${CORS_ORIGIN:-http://localhost:${FRONTEND_PORT}}"
PUBLIC_API_BASE_URL="${PUBLIC_API_BASE_URL:-http://localhost:${BACKEND_PORT}}"

# Detect primary LAN IP on macOS / Linux
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")"

echo ""
echo "============================================================"
echo " hdhr-open Development Servers Starting"
echo " Backend:  http://localhost:${BACKEND_PORT}  (LAN: http://${LAN_IP}:${BACKEND_PORT})"
echo " Frontend: http://localhost:${FRONTEND_PORT} (LAN: http://${LAN_IP}:${FRONTEND_PORT})"
echo "============================================================"
echo ""

(cd "$ROOT_DIR/backend" && uv sync && CORS_ORIGIN="$CORS_ORIGIN" uv run uvicorn app.main:app --reload --host "$HOST" --port "$BACKEND_PORT") &

(cd "$ROOT_DIR/frontend" && npm install && PUBLIC_API_BASE_URL="$PUBLIC_API_BASE_URL" npm run dev -- --host "$HOST" --port "$FRONTEND_PORT") &

wait
