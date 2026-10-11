# Configuration

Most day-to-day settings (Schedules Direct credentials, DVR engine, guide
sources, playback mode, etc.) are configured through the web UI after first
boot, under **Settings**. The environment variables below are the ones you
typically set once, before first boot.

## Backend (`backend/.env`)

Copy from `backend/.env.example`. The most relevant settings:

- `TIMEZONE` — used for recording filenames and schedule matching.
- `CORS_ORIGIN` — must allow the origin the frontend is served from (e.g.
  `http://192.168.1.50:3000`) or the browser will block API calls.
- `DB_PATH` / `SECRET_KEY_PATH` / `HDHOMERUN_MEDIA_CACHE_DIR` /
  `RECORDINGS_DIR` — storage paths, normally left at their local-dev
  defaults and only overridden by `docker-compose.yml` to point into a
  mounted volume.
- Cookie flags and `LOG_LEVEL` — see the comments in `.env.example` for the
  full list.

## Frontend (`frontend/.env`)

Copy from `frontend/.env.example`.

- `PUBLIC_API_BASE_URL` — base URL of the backend API (e.g.
  `http://localhost:8000` for local dev, or the backend host's LAN IP/port
  otherwise). Must match whatever `CORS_ORIGIN` on the backend allows.

## Docker-specific overrides

- `BACKEND_PORT` — publishes the backend on a different *host* port if
  `:8000` is already taken by something else on the Docker host. This only
  changes the published port; it never collides with another container,
  since each container has its own isolated network namespace.
- `UVICORN_PORT` — the port uvicorn binds to *inside* the container
  (defaults to `8000`). Only needed if something else inside that same
  container namespace needs port 8000.
- `RECORDINGS_PATH` — host directory for the recordings volume, if you want
  recordings on a NAS or large disk instead of the default Docker volume.
  Must be readable *and* writable by uid 1000.
- `HDHOMERUN_RECORDINGS_PATH` — host mount for the **HDHomeRun DVR**
  engine's own recording storage, so HDHR Open's commercial-detection
  pipeline can read (and write `.edl` files next to) those recordings. Must
  be readable by uid 1000 and read-write in the container. After setting
  it, enter `/app/hdhomerun-recordings` as the "Recordings path (local
  mount)" in **Settings → HDHomeRun network settings** and press **Test
  recordings mount**. See [DVR Guide](dvr.md#local-access-to-hdhomerun-dvr-recordings)
  for the full walkthrough.

See the comments in `docker-compose.yml` for the complete list and exact
syntax.

## Network exposure

There is no authentication in front of the HTTP server beyond the app's
own PIN-based profile login — treat the `ports:` mapping in your compose
file (or whatever reverse proxy you put in front of it) as the real
security perimeter. Don't expose this directly to the internet without a
reverse proxy and TLS in front of it.

The optional DVR SSH connection (for retention/cleanup on a HDHomeRun DVR
box) likewise does not pin host keys (`known_hosts=None`) — same LAN-trust
assumption as the HTTP calls above.

The backend is a single-SQLite-writer design — only run one instance of
the backend against a given `storage.db`.

Found a security issue? See the project's
[Security Policy](https://github.com/AndyG-0/hdhr-open/blob/main/SECURITY.md)
for how to report it privately.
