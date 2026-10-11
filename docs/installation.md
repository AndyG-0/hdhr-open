# Installation

HDHR Open runs two services: a FastAPI **backend** and a SvelteKit
**frontend**. Pick one of the paths below.

## Docker (recommended for self-hosting)

```sh
git clone https://github.com/AndyG-0/hdhr-open.git
cd hdhr-open
cp backend/.env.example backend/.env   # edit if you need to
docker compose up -d --build
```

This starts the backend on `:8000` and the frontend on `:3000`. Open
`http://<host>:3000` in a browser, or the host's LAN IP on the same
network. See `docker-compose.yml` for every environment variable the
services read.

=== "Different hosts for frontend/backend"

    If the frontend and backend are reachable at different hosts (not both
    `localhost`), set `CORS_ORIGIN` (backend) and `PUBLIC_API_BASE_URL`
    (frontend) to match — see [Configuration](configuration.md).

=== "Port 8000 already taken"

    Set `BACKEND_PORT` to publish the backend on a different host port
    instead, e.g.:

    ```sh
    BACKEND_PORT=18001 docker compose up -d
    ```

    and update `PUBLIC_API_BASE_URL` to match. This only changes the
    *published* host port — it can't collide with another container
    regardless, since each container has its own isolated network
    namespace. `UVICORN_PORT` (also env-overridable) controls what port
    uvicorn binds to *inside* the container, for the rare case something
    else inside that same namespace needs port 8000.

=== "Production / tagged images"

    For a tagged-image deployment (pulling from GHCR instead of building
    locally), use `docker-compose.prod.yml` instead:

    ```sh
    docker compose -f docker-compose.prod.yml up -d
    ```

=== "Podman (rootless)"

    Both compose files also run under rootless `podman-compose`, but need a
    couple of settings Docker doesn't — see
    [Hardware Acceleration → Podman](hardware-acceleration.md#podman-rootless)
    (the same settings apply whether or not you use hardware acceleration).

Recordings are stored in a Docker volume by default — see
[Configuration](configuration.md) for `RECORDINGS_PATH` and
`HDHOMERUN_RECORDINGS_PATH` if you want them on a NAS or need commercial
detection to read HDHomeRun DVR recordings.

Hardware-accelerated transcoding (VAAPI/Quick Sync/NVENC) needs a device
passed through to the container — see
[Hardware Acceleration](hardware-acceleration.md).

## Barebones (no Docker)

For running directly on the host without containers (e.g. a Raspberry Pi
you don't want to run Docker on), Debian, Ubuntu, Raspberry Pi OS, and other
Debian-based distributions (Pop!_OS, Linux Mint, Armbian, DietPi, etc.) have
a one-line installer. Sign in as the non-root account that should run HDHR
Open and run:

```bash
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/install.sh | bash
```

The installer requests `sudo`, installs apt-based dependencies (git,
build-essential, python3, Node.js 20, `uv`), checks out `main` to
`~/hdhr-open`, builds both backend and frontend, and enables them at boot
via systemd.

On first run, it interactively prompts for:

- **Timezone** (defaults to the host's own, via `timedatectl`).
- **Frontend API URL**: `PUBLIC_API_BASE_URL` in `frontend/.env` — defaults
  to the host's primary LAN IP, so other devices on your network can reach
  it (`CORS_ORIGIN` is derived from the same value).

To override the API URL non-interactively:

```bash
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/install.sh | bash -s -- --api-url http://192.168.1.50:8000
# or with an environment variable
HDHROPEN_PUBLIC_API_BASE_URL=http://192.168.1.50:8000 curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/install.sh | bash
```

To use a non-default install location, set `HDHROPEN_INSTALL_DIR=/your/path`.
First installation must run from an interactive terminal (or the
`--api-url`/env-var overrides above) so its setup prompts can configure
initial settings.

Rerun the installer later to fast-forward the checkout, rebuild, and
restart the services. It preserves `backend/.env`, `frontend/.env`, and the
SQLite database. If you have made Git changes in `~/hdhr-open`, the safe
fast-forward stops rather than overwriting them.

HDHR Open is then available locally at `http://localhost:3000`. On a
trusted LAN, use the host's IP address with port `3000` instead. Manage
services with:

```bash
sudo systemctl status hdhr-open-backend hdhr-open-frontend
journalctl -u hdhr-open-backend -u hdhr-open-frontend -f
```

Both services log to stdout/stderr only — journald captures it and applies
its own default size cap, which is usually fine but worth checking on a
small root filesystem (e.g. a Raspberry Pi's SD card):

```bash
journalctl --disk-usage
```

To set an explicit cap instead of relying on the default, add e.g.
`SystemMaxUse=200M` to `/etc/systemd/journald.conf` (or a drop-in under
`/etc/systemd/journald.conf.d/`) and restart with
`sudo systemctl restart systemd-journald`.

For updating or uninstalling an existing barebones install, see
[Updating & Uninstalling](updating.md).

### Manual setup

The installer is the supported path. These notes are for a manually
checked-out tree or custom service setup.

**Configure:**

- `backend/.env` — copy from `backend/.env.example`; set `TIMEZONE` and
  `CORS_ORIGIN` at minimum. Everything else (Schedules Direct credentials,
  DVR settings, etc.) is configured through the web UI after first boot.
- `frontend/.env` — copy from `frontend/.env.example`; set
  `PUBLIC_API_BASE_URL` (usually `http://localhost:8000` if both services
  run on the same host, or the host's LAN IP otherwise).

**Build:**

```bash
cd backend && uv sync
cd ../frontend && npm install && npm run build
```

**Install systemd services:**

```bash
sed \
  -e "s|__HDHROPEN_USER__|$USER|g" \
  -e "s|__HDHROPEN_BACKEND_DIR__|$HOME/hdhr-open/backend|g" \
  -e "s|__HDHROPEN_FRONTEND_DIR__|$HOME/hdhr-open/frontend|g" \
  deploy/hdhr-open-backend.service | sudo tee /etc/systemd/system/hdhr-open-backend.service >/dev/null
sed \
  -e "s|__HDHROPEN_USER__|$USER|g" \
  -e "s|__HDHROPEN_BACKEND_DIR__|$HOME/hdhr-open/backend|g" \
  -e "s|__HDHROPEN_FRONTEND_DIR__|$HOME/hdhr-open/frontend|g" \
  -e "s|__HDHROPEN_PUBLIC_API_BASE_URL__|http://localhost:8000|g" \
  deploy/hdhr-open-frontend.service | sudo tee /etc/systemd/system/hdhr-open-frontend.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now hdhr-open-backend hdhr-open-frontend
```

The backend unit is sandboxed (`ProtectSystem=strict`) with
`ReadWritePaths=` pointing at its own directory for `storage.db`,
`secret.key`, the media cache, and recordings — if you relocate the
checkout or set `DB_PATH`/`RECORDINGS_DIR`/etc. to somewhere else, update
`ReadWritePaths=` to match, or those writes will fail. Only run one
instance of this unit against a given `storage.db` — see
[Configuration → Network exposure](configuration.md#network-exposure) for
why (single SQLite writer, not a multi-process design).

Deploying behind a reverse proxy instead of exposing services directly on
the LAN? See the `ports:` comments in `docker-compose.yml` and
`docker-compose.prod.yml` for the supported `127.0.0.1:PORT:PORT` binding
pattern, and [Configuration → Network exposure](configuration.md#network-exposure)
for the full picture. The `PORT:PORT` default (bound to all interfaces)
stays the default — this product's core self-hosting use case is LAN
access.

For `ffmpeg`/hardware-acceleration setup on a barebones install, see
[Hardware Acceleration](hardware-acceleration.md).

## Local development

```sh
./dev.sh
```

Starts the backend (`uvicorn --reload`) on `:8100` and the frontend (Vite
dev server) on `:5273` — offset from the stock 8000/5173 ports so this can
run alongside another local project using the defaults. First run copies
`backend/.env.example` → `backend/.env` and `frontend/.env.example` →
`frontend/.env` automatically.

See `backend/README.md` and `frontend/README.md` in the repository for
component-specific development details (tests, linting, project layout).
