#!/bin/sh
set -e

# A bind-mounted host file that doesn't exist yet becomes an empty directory
# inside the container (Docker's default behavior for a missing bind-mount
# source), which turns into a silently-empty config (pydantic-settings
# quietly skips a directory where it expects `.env`) instead of a clear,
# actionable failure. Catch it here.
if [ -d /app/.env ]; then
    echo "ERROR: /app/.env is a directory, not a file." >&2
    echo "This usually means backend/.env was never created on the host before starting Docker." >&2
    echo "Run 'cp backend/.env.example backend/.env', then restart the container." >&2
    exit 1
fi

exec "$@"
