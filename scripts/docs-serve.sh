#!/usr/bin/env bash
# Serves the MkDocs user guide (docs/) locally with live-reload, for
# previewing changes before they're published by .github/workflows/pages.yml.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

command -v uv >/dev/null 2>&1 || {
	printf 'docs-serve.sh: missing required command: uv\n' >&2
	printf 'Install it: https://docs.astral.sh/uv/getting-started/installation/\n' >&2
	exit 1
}

exec uv tool run --with-requirements docs/requirements.txt mkdocs serve "$@"
