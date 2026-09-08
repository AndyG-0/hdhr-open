#!/usr/bin/env bash
# Bumps VERSION (major/minor/patch), syncs backend/pyproject.toml,
# frontend/package.json, and their lockfiles, then
# commits and tags a release.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly RELEASE_BRANCH="${HDHROPEN_RELEASE_BRANCH:-main}"

fail() { printf 'release.sh: %s\n' "$*" >&2; exit 1; }
info() { printf '\n==> %s\n' "$*"; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"; }

usage() {
	cat <<'EOF'
Usage: scripts/release.sh <major|minor|patch> [--push] [-y|--yes]

Bumps the version in VERSION, backend/pyproject.toml, and
frontend/package.json, regenerates backend/uv.lock and
frontend/package-lock.json, commits, and creates an annotated git
tag vX.Y.Z. Requires a clean working tree on the release branch
(default "main"; override with HDHROPEN_RELEASE_BRANCH).

  --push     Also push the branch and tag to origin. Omitted by default —
             the commit/tag are left local to review before pushing.
  -y, --yes  Skip the confirmation prompt.
EOF
}

BUMP=""
PUSH=false
ASSUME_YES=false
while [[ $# -gt 0 ]]; do
	case "$1" in
	major | minor | patch) BUMP="$1" ;;
	--push) PUSH=true ;;
	-y | --yes) ASSUME_YES=true ;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		usage
		fail "Unknown argument: $1"
		;;
	esac
	shift
done
[[ -n "$BUMP" ]] || {
	usage
	fail "Specify a bump type: major, minor, or patch."
}

require_command git
require_command uv
require_command npm
require_command node

cd "$ROOT_DIR"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "Not inside a git repository."

current_branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "$current_branch" == "$RELEASE_BRANCH" ]] 	|| fail "Must be on '$RELEASE_BRANCH' (currently on '$current_branch')."

[[ -z "$(git status --porcelain)" ]] 	|| fail "Working tree is not clean. Commit or stash changes first."

if git remote get-url origin >/dev/null 2>&1; then
	info "Fetching origin/$RELEASE_BRANCH"
	git fetch --quiet origin "$RELEASE_BRANCH"
	[[ "$(git rev-parse "$RELEASE_BRANCH")" == "$(git rev-parse "origin/$RELEASE_BRANCH")" ]] 		|| fail "Local $RELEASE_BRANCH has diverged from origin/$RELEASE_BRANCH. Sync first so the tag lands on a commit CI has actually run on."
fi

root_version="$(<"$ROOT_DIR/VERSION")"
[[ "$root_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] 	|| fail "VERSION ('$root_version') is not a plain X.Y.Z semver."

backend_version="$(cd "$ROOT_DIR/backend" && uv version --short)"
[[ "$backend_version" == "$root_version" ]] 	|| fail "VERSION ($root_version) and backend/pyproject.toml ($backend_version) are out of sync. Reconcile manually first."

frontend_version="$(cd "$ROOT_DIR/frontend" && node -p "require('./package.json').version")"
[[ "$frontend_version" == "$root_version" ]] 	|| fail "VERSION ($root_version) and frontend/package.json ($frontend_version) are out of sync. Reconcile manually first."

new_version="$(cd "$ROOT_DIR/backend" && uv version --bump "$BUMP" --dry-run --short)"

info "Releasing v$root_version -> v$new_version"
if [[ "$ASSUME_YES" != true ]]; then
	read -r -p "Continue? [y/N] " reply </dev/tty
	[[ "$reply" =~ ^[Yy]$ ]] || fail "Aborted."
fi

info "Bumping backend/pyproject.toml and re-locking backend/uv.lock"
(cd "$ROOT_DIR/backend" && uv version --bump "$BUMP" --no-sync)

info "Bumping frontend/package.json and frontend/package-lock.json"
(cd "$ROOT_DIR/frontend" && npm version "$new_version" --no-git-tag-version >/dev/null)

info "Writing VERSION"
printf '%s\n' "$new_version" >"$ROOT_DIR/VERSION"

git add VERSION backend/pyproject.toml backend/uv.lock frontend/package.json frontend/package-lock.json
git commit -m "Release v$new_version"
git tag -a "v$new_version" -m "Release v$new_version"

info "Created commit and tag v$new_version"

if [[ "$PUSH" == true ]]; then
	info "Pushing $RELEASE_BRANCH and v$new_version"
	git push origin "$RELEASE_BRANCH"
	git push origin "v$new_version"
else
	cat <<EOF

Not pushed. When ready:

  git push origin $RELEASE_BRANCH
  git push origin v$new_version

Pushing the tag triggers .github/workflows/publish-images.yml (GHCR images)
and .github/workflows/release.yml (the GitHub Release).
EOF
fi
