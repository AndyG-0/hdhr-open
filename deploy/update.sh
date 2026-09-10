#!/usr/bin/env bash
# Fast-forward a native HDHR Open installation to the latest code on the
# configured branch, rebuild both services, and restart them.  Safe to
# re-run; preserves backend/.env, frontend/.env, and storage.db.
#
# Run as the non-root account that owns the installation:
#   bash ~/hdhr-open/deploy/update.sh
#
# Or as a one-liner:
#   curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/update.sh | bash
set -euo pipefail
IFS=$'\n\t'

readonly REPOSITORY_REF="${HDHROPEN_REPOSITORY_REF:-main}"

INSTALL_HOME=""
INSTALL_DIR=""
BACKEND_DIR=""
FRONTEND_DIR=""

fail() {
  printf 'HDHR Open update failed: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '\n==> %s\n' "$*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

detect_install_user() {
  if [[ "${EUID}" -eq 0 ]]; then
    fail "Run this as the non-root account that owns the HDHR Open installation."
  fi
  INSTALL_HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
  [[ -n "$INSTALL_HOME" && -d "$INSTALL_HOME" ]] || fail "Could not determine home directory."
  INSTALL_DIR="${HDHROPEN_INSTALL_DIR:-$INSTALL_HOME/hdhr-open}"
  BACKEND_DIR="$INSTALL_DIR/backend"
  FRONTEND_DIR="$INSTALL_DIR/frontend"
}

check_install_dir() {
  [[ -d "$INSTALL_DIR/.git" ]] || fail "$INSTALL_DIR is not an HDHR Open Git checkout.  Set HDHROPEN_INSTALL_DIR or run install.sh first."
  [[ -f "$BACKEND_DIR/.env" ]] || fail "No backend/.env found in $INSTALL_DIR.  Run install.sh first."
}

sync_repository() {
  info "Fetching latest code"
  git -C "$INSTALL_DIR" fetch --quiet origin "$REPOSITORY_REF"
  # Abort if local changes would prevent a fast-forward.
  git -C "$INSTALL_DIR" merge --ff-only "origin/$REPOSITORY_REF"
}

build_application() {
  local uv_bin
  uv_bin="$(getent passwd "$(id -un)" | cut -d: -f6)/.local/bin/uv"
  PATH="$(dirname "$uv_bin"):$PATH"
  export PATH
  require_command uv

  info "Installing backend dependencies"
  (cd "$BACKEND_DIR" && uv sync)

  info "Building frontend"
  (cd "$FRONTEND_DIR" && npm ci && npm run build)
}

restart_services() {
  info "Restarting services"
  sudo systemctl restart hdhr-open-backend.service hdhr-open-frontend.service
}

wait_for_health() {
  info "Waiting for the backend health check"
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/api/health >/dev/null; then
      return
    fi
    sleep 2
  done
  sudo systemctl --no-pager --full status hdhr-open-backend.service || true
  fail "The backend did not become healthy.  Review the service logs above."
}

print_completion() {
  local version
  version="$(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo 'unknown')"
  printf '\nHDHR Open updated to v%s and is running at http://localhost:3000\n' "$version"
  printf 'View logs: journalctl -u hdhr-open-backend -u hdhr-open-frontend -f\n'
}

main() {
  require_command sudo
  require_command git
  require_command curl
  sudo -v
  detect_install_user
  check_install_dir
  sync_repository
  build_application
  restart_services
  wait_for_health
  print_completion
}

if [[ "${BASH_SOURCE[0]:-}" == "${0:-}" || "${#BASH_SOURCE[@]}" -eq 0 ]]; then
  main "$@"
fi
