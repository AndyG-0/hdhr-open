#!/usr/bin/env bash
# Installs or upgrades HDHR Open from the public main branch on apt-based Linux.
set -euo pipefail
IFS=$'\n\t'

readonly REPOSITORY_URL="${HDHROPEN_REPOSITORY_URL:-https://github.com/andyg-0/hdhr-open.git}"
readonly REPOSITORY_REF="${HDHROPEN_REPOSITORY_REF:-main}"
OS_RELEASE_FILE="${HDHROPEN_OS_RELEASE_FILE:-/etc/os-release}"
readonly NODE_SETUP_URL="https://deb.nodesource.com/setup_20.x"
SYSTEMD_DIR="${HDHROPEN_SYSTEMD_DIR:-/etc/systemd/system}"

INSTALL_USER="${INSTALL_USER:-}"
INSTALL_HOME="${INSTALL_HOME:-}"
INSTALL_DIR="${INSTALL_DIR:-}"
BACKEND_DIR="${BACKEND_DIR:-}"
FRONTEND_DIR="${FRONTEND_DIR:-}"
CUSTOM_API_URL=""

fail() {
  printf 'HDHR Open install failed: %s\n' "$*" >&2
  exit 1
}

info() {
  printf '\n==> %s\n' "$*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --api-url|--backend-url)
        local api_url_flag="$1"
        shift
        [[ $# -gt 0 ]] || fail "Missing argument for $api_url_flag"
        CUSTOM_API_URL="$1"
        shift
        ;;
      --api-url=*|--backend-url=*)
        CUSTOM_API_URL="${1#*=}"
        shift
        ;;
      --uninstall)
        shift
        local script_source uninstall_script
        script_source="${BASH_SOURCE[0]:-}"
        uninstall_script=""
        if [[ -n "$script_source" && "$script_source" != "bash" && "$script_source" != "-" && -f "$script_source" ]]; then
          uninstall_script="$(cd "$(dirname "$script_source")" 2>/dev/null && pwd)/uninstall.sh"
        fi
        if [[ -n "$uninstall_script" && -f "$uninstall_script" ]]; then
          exec bash "$uninstall_script" "$@"
        else
          require_command curl
          curl -fsSL "https://raw.githubusercontent.com/andyg-0/hdhr-open/$REPOSITORY_REF/deploy/uninstall.sh" | bash -s -- "$@"
          exit $?
        fi
        ;;
      -h|--help)
        printf 'HDHR Open Linux Installer\n\n'
        printf 'Usage: install.sh [options]\n\n'
        printf 'Options:\n'
        printf '  --api-url URL     Set PUBLIC_API_BASE_URL for the frontend (default: http://<lan-ip>:8000)\n'
        printf '  --uninstall       Uninstall HDHR Open services and cleanup files (delegates to uninstall.sh)\n'
        printf '  -h, --help        Show this help message\n\n'
        printf 'Environment variables:\n'
        printf '  HDHROPEN_INSTALL_DIR           Custom install destination (default: ~/hdhr-open)\n'
        printf '  HDHROPEN_PUBLIC_API_BASE_URL   Custom frontend backend API URL\n'
        exit 0
        ;;
      *)
        fail "Unknown option '$1'. Use --help for usage."
        ;;
    esac
  done
}

detect_install_user() {
  if [[ "${EUID}" -eq 0 ]]; then
    fail "Run this as the non-root account that should run HDHR Open; the installer will request sudo when needed."
  fi

  INSTALL_USER="$(id -un)"
  if [[ -z "${INSTALL_HOME:-}" ]]; then
    if command -v getent >/dev/null 2>&1; then
      INSTALL_HOME="$(getent passwd "$INSTALL_USER" 2>/dev/null | cut -d: -f6 || true)"
    fi
    if [[ -z "${INSTALL_HOME:-}" ]]; then
      INSTALL_HOME="${HOME:-}"
    fi
  fi
  [[ -n "$INSTALL_HOME" && -d "$INSTALL_HOME" ]] || fail "Could not determine the home directory for $INSTALL_USER."

  INSTALL_DIR="${HDHROPEN_INSTALL_DIR:-$INSTALL_HOME/hdhr-open}"
  BACKEND_DIR="$INSTALL_DIR/backend"
  FRONTEND_DIR="$INSTALL_DIR/frontend"
}

validate_platform() {
  [[ -r "$OS_RELEASE_FILE" ]] || fail "Cannot read $OS_RELEASE_FILE to identify this Linux distribution."
  # shellcheck disable=SC1090
  source "$OS_RELEASE_FILE"

  local is_debian_like=false
  case "${ID:-}" in
    debian|ubuntu|raspbian|pop|linuxmint|elementary|zorin|armbian|dietpi|devuan|kali|pureos|tuxedo|neon)
      is_debian_like=true
      ;;
    *)
      for like in ${ID_LIKE:-}; do
        if [[ "$like" == "debian" || "$like" == "ubuntu" ]]; then
          is_debian_like=true
          break
        fi
      done
      ;;
  esac

  if [[ "$is_debian_like" != true ]] && command -v apt-get >/dev/null 2>&1; then
    is_debian_like=true
  fi

  if [[ "$is_debian_like" != true ]]; then
    fail "Unsupported distribution '${ID:-unknown}'. HDHR Open's installer supports Debian, Ubuntu, Raspberry Pi OS, and other Debian-based distributions."
  fi

  case "$(uname -m)" in
    x86_64|aarch64|arm64|armv7l) ;;
    *) fail "Unsupported architecture '$(uname -m)'. Supported: x86_64, aarch64, arm64, armv7l." ;;
  esac
}

install_system_dependencies() {
  info "Installing system dependencies"
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl git build-essential python3

  if ! command -v node >/dev/null 2>&1 || [[ "$(node --version | sed 's/^v//' | cut -d. -f1)" -lt 20 ]]; then
    info "Installing Node.js 20"
    curl -fsSL "$NODE_SETUP_URL" | sudo -E bash -
    sudo apt-get install -y nodejs
  fi
}

install_uv() {
  if [[ ! -x "$INSTALL_HOME/.local/bin/uv" ]]; then
    info "Installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="$INSTALL_HOME/.local/bin:$PATH"
  require_command uv
}

sync_repository() {
  info "Fetching HDHR Open"
  if [[ -e "$INSTALL_DIR" && ! -d "$INSTALL_DIR/.git" ]]; then
    fail "$INSTALL_DIR already exists but is not an HDHR Open Git checkout. Move it aside or set HDHROPEN_INSTALL_DIR."
  fi

  if [[ -d "$INSTALL_DIR/.git" ]]; then
    git -C "$INSTALL_DIR" fetch --quiet origin "$REPOSITORY_REF"
    git -C "$INSTALL_DIR" checkout "$REPOSITORY_REF"
    git -C "$INSTALL_DIR" merge --ff-only "origin/$REPOSITORY_REF"
  else
    git clone --branch "$REPOSITORY_REF" --single-branch "$REPOSITORY_URL" "$INSTALL_DIR"
  fi
}

set_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  python3 - "$file" "$key" "$value" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
prefix = f"{key}="
lines = path.read_text().splitlines()
for index, line in enumerate(lines):
    if line.startswith(prefix):
        lines[index] = prefix + value
        break
else:
    lines.append(prefix + value)
path.write_text("\n".join(lines) + "\n")
PY
}

get_env_value() {
  local file="$1" key="$2"
  if [[ -f "$file" ]]; then
    grep -E "^${key}=" "$file" 2>/dev/null | tail -n 1 | cut -d= -f2- || true
  fi
}

detect_system_timezone() {
  local tz=""
  if command -v timedatectl >/dev/null 2>&1; then
    tz="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
  fi
  if [[ -z "$tz" && -f /etc/timezone ]]; then
    tz="$(cat /etc/timezone 2>/dev/null || true)"
  fi
  if [[ -z "$tz" && -L /etc/localtime ]]; then
    tz="$(readlink /etc/localtime 2>/dev/null | sed 's#.*/zoneinfo/##' || true)"
  fi
  printf '%s' "${tz:-UTC}"
}

detect_primary_lan_ip() {
  local addresses addr addr_list
  addresses="$(hostname -I 2>/dev/null || true)"
  if [[ -n "$addresses" ]]; then
    IFS=' ' read -ra addr_list <<<"$addresses"
    for addr in "${addr_list[@]}"; do
      if [[ "$addr" != *:* && "$addr" != 127.* ]]; then
        printf '%s' "$addr"
        return
      fi
    done
  fi
}

detect_default_api_url() {
  if [[ -n "${CUSTOM_API_URL:-}" ]]; then
    printf '%s' "$CUSTOM_API_URL"
    return
  fi
  if [[ -n "${HDHROPEN_PUBLIC_API_BASE_URL:-}" ]]; then
    printf '%s' "$HDHROPEN_PUBLIC_API_BASE_URL"
    return
  fi
  local lan_ip
  lan_ip="$(detect_primary_lan_ip)"
  if [[ -n "$lan_ip" ]]; then
    printf 'http://%s:8000' "$lan_ip"
  else
    printf 'http://localhost:8000'
  fi
}

configure_timezone_and_cors() {
  local timezone default_tz api_url
  [[ -r /dev/tty ]] || fail "First-run configuration needs an interactive terminal. Run the installer from a terminal session, or pre-populate backend/.env and frontend/.env yourself."
  default_tz="$(detect_system_timezone)"
  read -r -p "Timezone [$default_tz]: " timezone </dev/tty
  timezone="${timezone:-$default_tz}"
  set_env_value "$BACKEND_DIR/.env" TIMEZONE "$timezone"

  api_url="$(detect_default_api_url)"
  if [[ -z "${CUSTOM_API_URL:-}" && -z "${HDHROPEN_PUBLIC_API_BASE_URL:-}" ]]; then
    local input
    read -r -p "Frontend API Base URL [$api_url]: " input </dev/tty
    api_url="${input:-$api_url}"
  fi
  set_env_value "$FRONTEND_DIR/.env" PUBLIC_API_BASE_URL "$api_url"
  # CORS_ORIGIN must match wherever the browser actually loads the frontend
  # from — same reasoning as docker-compose.yml's CORS_ORIGIN override.
  local frontend_origin="${api_url%:8000}:3000"
  set_env_value "$BACKEND_DIR/.env" CORS_ORIGIN "$frontend_origin"
}

prepare_configuration() {
  local first_install=false
  if [[ ! -f "$BACKEND_DIR/.env" ]]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    first_install=true
  fi
  if [[ ! -f "$FRONTEND_DIR/.env" ]]; then
    cp "$FRONTEND_DIR/.env.example" "$FRONTEND_DIR/.env"
  fi
  chmod 600 "$BACKEND_DIR/.env"

  # Ensure PUBLIC_API_BASE_URL has a working value on upgrade or non-interactive installs.
  local current_api_url
  current_api_url="$(get_env_value "$FRONTEND_DIR/.env" PUBLIC_API_BASE_URL)"
  if [[ -n "${CUSTOM_API_URL:-}" || -n "${HDHROPEN_PUBLIC_API_BASE_URL:-}" ]]; then
    set_env_value "$FRONTEND_DIR/.env" PUBLIC_API_BASE_URL "$(detect_default_api_url)"
  elif [[ -z "$current_api_url" && "$first_install" != true ]]; then
    set_env_value "$FRONTEND_DIR/.env" PUBLIC_API_BASE_URL "$(detect_default_api_url)"
  fi

  printf '%s' "$first_install"
}

build_application() {
  info "Installing application dependencies"
  (cd "$BACKEND_DIR" && uv sync)
  (cd "$FRONTEND_DIR" && npm ci && npm run build)
}

render_service_units() {
  local service template temporary api_base_url
  api_base_url="$(get_env_value "$FRONTEND_DIR/.env" PUBLIC_API_BASE_URL)"
  api_base_url="${api_base_url:-$(detect_default_api_url)}"

  for service in hdhr-open-backend hdhr-open-frontend; do
    template="$INSTALL_DIR/deploy/$service.service"
    temporary="$(mktemp)"
    python3 - "$template" "$temporary" "$INSTALL_USER" "$BACKEND_DIR" "$FRONTEND_DIR" "$api_base_url" <<'PY'
from pathlib import Path
import sys

template = Path(sys.argv[1])
destination = Path(sys.argv[2])
user = sys.argv[3]
backend = sys.argv[4]
frontend = sys.argv[5]
api_base_url = sys.argv[6]

content = template.read_text()
content = content.replace("__HDHROPEN_USER__", user)
content = content.replace("__HDHROPEN_BACKEND_DIR__", backend)
content = content.replace("__HDHROPEN_FRONTEND_DIR__", frontend)
content = content.replace("__HDHROPEN_PUBLIC_API_BASE_URL__", api_base_url)
destination.write_text(content)
PY
    sudo install -m 644 "$temporary" "$SYSTEMD_DIR/$service.service"
    rm -f "$temporary"
  done

  sudo systemctl daemon-reload
  sudo systemctl enable --now hdhr-open-backend.service hdhr-open-frontend.service
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
  fail "The backend did not become healthy. Review the service logs above."
}

print_completion() {
  local addresses addr api_base
  addresses="$(hostname -I 2>/dev/null || true)"
  api_base="$(get_env_value "$FRONTEND_DIR/.env" PUBLIC_API_BASE_URL)"
  printf '\nHDHR Open is running at http://localhost:3000\n'
  if [[ -n "$addresses" ]]; then
    for addr in $addresses; do
      if [[ "$addr" != *:* && "$addr" != 127.* ]]; then
        printf 'LAN access:      http://%s:3000\n' "$addr"
      fi
    done
  fi
  if [[ -n "$api_base" ]]; then
    printf 'Frontend API:    %s\n' "$api_base"
  fi
  printf 'Manage services: sudo systemctl status hdhr-open-backend hdhr-open-frontend\n'
  printf 'View logs:       journalctl -u hdhr-open-backend -u hdhr-open-frontend -f\n'
  printf 'Configuration:   %s/backend/.env and %s/frontend/.env\n' "$INSTALL_DIR" "$INSTALL_DIR"
  printf 'Hardware transcoding: disabled by default — see deploy/README.md.\n'
  printf 'Rerun this installer later to fast-forward, rebuild, and restart HDHR Open.\n'
}

install_sudoers_restart() {
  local sudoers_file="/etc/sudoers.d/hdhr-open-restart"
  local restart_script="$INSTALL_DIR/deploy/restart.sh"
  # Make the restart wrapper executable.
  chmod 755 "$restart_script"
  # Write a targeted sudoers rule granting only this one script, no-password.
  # visudo -c validates the syntax before it's put in place.
  local tmp_sudoers
  tmp_sudoers="$(mktemp)"
  printf '# HDHR Open: allow the service user to restart hdhr-open services only.\n' >"$tmp_sudoers"
  printf '%s ALL=(root) NOPASSWD: %s\n' "$INSTALL_USER" "$restart_script" >>"$tmp_sudoers"
  if visudo -c -f "$tmp_sudoers" >/dev/null 2>&1; then
    sudo install -m 440 "$tmp_sudoers" "$sudoers_file"
  else
    rm -f "$tmp_sudoers"
    fail "Generated sudoers file failed validation — not installing."
  fi
  rm -f "$tmp_sudoers"
}

main() {
  parse_args "$@"
  require_command sudo
  sudo -v
  detect_install_user
  validate_platform
  install_system_dependencies
  install_uv
  sync_repository
  local first_install
  first_install="$(prepare_configuration)"
  build_application
  if [[ "$first_install" == true ]]; then
    info "First-run configuration"
    configure_timezone_and_cors
  fi
  render_service_units
  install_sudoers_restart
  wait_for_health
  print_completion
}

if [[ "${BASH_SOURCE[0]:-}" == "${0:-}" || "${#BASH_SOURCE[@]}" -eq 0 ]]; then
  main "$@"
fi
