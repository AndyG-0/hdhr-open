#!/usr/bin/env bash
# Uninstalls HDHR Open native services and sudoers configuration, and
# optionally removes application files.
set -euo pipefail
IFS=$'\n\t'

SYSTEMD_DIR="${HDHROPEN_SYSTEMD_DIR:-${SYSTEMD_DIR:-/etc/systemd/system}}"
SUDOERS_FILE="${HDHROPEN_SUDOERS_FILE:-${SUDOERS_FILE:-/etc/sudoers.d/hdhr-open-restart}}"

INSTALL_USER="${INSTALL_USER:-}"
INSTALL_HOME="${INSTALL_HOME:-}"
INSTALL_DIR="${INSTALL_DIR:-}"
KEEP_DATA=false
FORCE=false

fail() {
  printf 'HDHR Open uninstall failed: %s\n' "$*" >&2
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
      -y|--yes|--force|-f)
        FORCE=true
        shift
        ;;
      --keep-data|--keep-files)
        KEEP_DATA=true
        shift
        ;;
      --purge|--all)
        KEEP_DATA=false
        shift
        ;;
      --install-dir)
        shift
        [[ $# -gt 0 ]] || fail "Missing argument for --install-dir"
        INSTALL_DIR="$1"
        shift
        ;;
      --install-dir=*)
        INSTALL_DIR="${1#*=}"
        shift
        ;;
      -h|--help)
        printf 'HDHR Open Linux Uninstaller\n\n'
        printf 'Usage: uninstall.sh [options]\n\n'
        printf 'Options:\n'
        printf '  -y, --yes, --force   Non-interactive mode; proceed without prompting\n'
        printf '  --keep-data          Keep configuration files, database, and repository in ~/hdhr-open\n'
        printf '  --purge, --all       Remove all files including the installation directory (default)\n'
        printf '  --install-dir DIR    Custom install directory (default: ~/hdhr-open)\n'
        printf '  -h, --help           Show this help message\n\n'
        printf 'Environment variables:\n'
        printf '  HDHROPEN_INSTALL_DIR    Custom install destination (default: ~/hdhr-open)\n'
        printf '  HDHROPEN_NONINTERACTIVE Set to 1/true to skip confirmation prompts\n'
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
    fail "Run this as the non-root account that owns the HDHR Open installation; the uninstaller will request sudo when needed."
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

  if [[ -z "$INSTALL_DIR" ]]; then
    INSTALL_DIR="${HDHROPEN_INSTALL_DIR:-$INSTALL_HOME/hdhr-open}"
  fi
}

self_relocate_if_needed() {
  if [[ "${HDHROPEN_UNINSTALL_RELOCATED:-}" == "true" ]]; then
    trap 'rm -f "${BASH_SOURCE[0]}" 2>/dev/null || true' EXIT
    return
  fi

  local script_source="${BASH_SOURCE[0]:-}"
  if [[ -n "$script_source" && "$script_source" != "bash" && "$script_source" != "-" && -f "$script_source" ]]; then
    local script_dir script_file
    script_dir="$(cd "$(dirname "$script_source")" 2>/dev/null && pwd)"
    script_file="$script_dir/$(basename "$script_source")"

    if [[ -n "$INSTALL_DIR" && "$script_file" == "$INSTALL_DIR"/* ]]; then
      local tmp_script
      tmp_script="$(mktemp "${TMPDIR:-/tmp}/hdhr-open-uninstall.XXXXXX.sh")"
      cp "$script_file" "$tmp_script"
      chmod 700 "$tmp_script"
      export HDHROPEN_UNINSTALL_RELOCATED=true
      cd "${HOME:-/tmp}"
      exec bash "$tmp_script" "$@"
    fi
  fi

  if [[ -n "$INSTALL_DIR" && "$PWD" == "$INSTALL_DIR"* ]]; then
    cd "${HOME:-/tmp}"
  fi
}

confirm_uninstall() {
  if [[ "$FORCE" == true || "${HDHROPEN_NONINTERACTIVE:-}" == "true" || "${HDHROPEN_NONINTERACTIVE:-}" == "1" ]]; then
    return
  fi

  [[ -r /dev/tty ]] || fail "Uninstall confirmation needs an interactive terminal. Run with -y/--force, or from a terminal session."

  printf 'This will remove HDHR Open services and sudoers rules.\n'
  if [[ "$KEEP_DATA" == true ]]; then
    printf 'Installation directory (%s) will be KEPT.\n' "$INSTALL_DIR"
  else
    printf 'Installation directory (%s) and all data will be REMOVED.\n' "$INSTALL_DIR"
  fi
  local answer
  read -r -p "Are you sure you want to uninstall HDHR Open? (y/N) [N]: " answer </dev/tty
  case "$answer" in
    [Yy]|[Yy][Ee][Ss]) ;;
    *)
      printf 'Uninstall cancelled.\n'
      exit 0
      ;;
  esac
}

stop_and_remove_services() {
  info "Stopping and removing systemd services"
  local service_removed=false

  for service in hdhr-open-backend hdhr-open-frontend; do
    if sudo systemctl is-active --quiet "$service.service" 2>/dev/null; then
      sudo systemctl stop "$service.service" 2>/dev/null || true
    fi
    if sudo systemctl is-enabled --quiet "$service.service" 2>/dev/null; then
      sudo systemctl disable "$service.service" 2>/dev/null || true
    fi
    if [[ -f "$SYSTEMD_DIR/$service.service" ]]; then
      sudo rm -f "$SYSTEMD_DIR/$service.service"
      service_removed=true
    fi
  done

  if [[ "$service_removed" == true ]]; then
    sudo systemctl daemon-reload 2>/dev/null || true
    sudo systemctl reset-failed 2>/dev/null || true
  fi
}

remove_sudoers_rule() {
  if [[ -f "$SUDOERS_FILE" ]]; then
    info "Removing sudoers restart rule"
    sudo rm -f "$SUDOERS_FILE"
  fi
}

remove_install_files() {
  if [[ "$KEEP_DATA" == true ]]; then
    info "Preserving installation files at $INSTALL_DIR"
    return
  fi

  if [[ -d "$INSTALL_DIR" ]]; then
    [[ -d "$INSTALL_DIR/.git" ]] || fail "$INSTALL_DIR does not look like an HDHR Open installation (no .git directory found); refusing to delete it. Pass --install-dir to point at the correct location, or use --keep-data to skip file removal."
    info "Removing installation directory ($INSTALL_DIR)"
    rm -rf "$INSTALL_DIR"
  fi
}

print_completion() {
  printf '\n==> HDHR Open has been uninstalled.\n'
  if [[ "$KEEP_DATA" == true ]]; then
    printf 'Services and configurations removed. Your files remain at: %s\n' "$INSTALL_DIR"
  else
    printf 'All services, configurations, and application files have been removed.\n'
  fi
}

main() {
  parse_args "$@"
  require_command sudo
  sudo -v
  detect_install_user
  self_relocate_if_needed "$@"
  confirm_uninstall
  stop_and_remove_services
  remove_sudoers_rule
  remove_install_files
  print_completion
}

if [[ "${BASH_SOURCE[0]:-}" == "${0:-}" || "${#BASH_SOURCE[@]}" -eq 0 ]]; then
  main "$@"
fi
