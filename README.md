# HDHR Open

[![CI](https://github.com/AndyG-0/hdhr-open/actions/workflows/ci.yml/badge.svg)](https://github.com/AndyG-0/hdhr-open/actions/workflows/ci.yml)
[![CodeQL](https://github.com/AndyG-0/hdhr-open/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/AndyG-0/hdhr-open/security/code-scanning)
[![License: MIT](https://img.shields.io/github/license/AndyG-0/hdhr-open)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/AndyG-0/hdhr-open)](https://github.com/AndyG-0/hdhr-open/releases/latest)

A self-hosted server and web client for watching and recording live TV
through an [HDHomeRun](https://www.silicondust.com/) network tuner. Point it
at your tuner, get a channel guide and live player in your browser, and
(optionally) record shows through SiliconDust's official DVR service.

This is not a general-purpose dashboard — it does one thing: HDHomeRun guide,
playback, and recording. See [`ROADMAP.md`](ROADMAP.md) for where it's headed
(multi-source guides, self-hosted recording, native apps).

## Features

- **Live guide + player** — channel lineup with program info, tune in with
  one click. Playback works either by transcoding server-side to H.264
  (`server_transcode`, works with any tuner but costs CPU per viewer) or by
  handing a raw stream link to an external player like VLC (`external`).
- **Optional hardware-accelerated transcoding** — VAAPI/Quick Sync support
  with a built-in diagnostics page (Settings → playback) to verify the
  container actually has GPU access before relying on it.
- **DVR** — dual-engine recording support with either HDHR Open's Built-in
  self-hosted DVR or SiliconDust's official HDHomeRun DVR engine. Supports
  cross-provider Series ID enrichment (matching XMLTV airings against
  HDHomeRun Cloud) and automatic fallback with user notifications when a Series
  ID cannot be resolved. Browse in-progress and completed recordings, and seek
  within recordings in `server_transcode` mode. See [`docs/dvr-usage-guide.md`](docs/dvr-usage-guide.md)
  for details on guide matching, Series IDs, and fallback behavior.
- **Multi-user profiles** — PIN-protected household profiles with
  admin/member roles, one browser session per device.
- **Multi-language UI** — English, Spanish, French, German.

## Architecture

- **`backend/`** — FastAPI (Python 3.12), no ORM (raw `sqlite3`), single
  household / single-tuner data model. See `backend/README.md`.
- **`frontend/`** — SvelteKit 2 / Svelte 5, using `mpegts.js` for in-browser
  playback (MSE). `frontend/src/lib/api.ts` is the single point of contact
  with the backend REST API.
- **`apple/`** — Native Apple TV (tvOS) and iOS client apps sharing a unified
  Swift framework (`HDHROpenKit`). See `apple/README.md`.
- **`android/`** — Native Android mobile client app built with Jetpack Compose
  and a shared core module (`core`). See `android/README.md`.

## Running it

### Docker (recommended for self-hosting)

```sh
cp backend/.env.example backend/.env   # edit if you need to
docker compose up -d --build
```

This starts the backend on `:8000` and the frontend on `:3000`. Open
`http://<host>:3000` in a browser, or `http://<host>:3000` on the same
LAN — see `docker-compose.yml` for the environment variables that need to
change when the frontend and backend are reachable at different hosts
(`CORS_ORIGIN`, `PUBLIC_API_BASE_URL`).

If port 8000 is already taken on the host (e.g. another project running
alongside this one), set `BACKEND_PORT` to publish the backend on a
different host port instead — e.g. `BACKEND_PORT=18001 docker compose up -d`
— and update `PUBLIC_API_BASE_URL` to match. This only changes the
published host port; it can't collide with another container regardless,
since each container has its own isolated network namespace — the internal
port doesn't need to change for that. `UVICORN_PORT` (also env-overridable)
controls what port uvicorn binds to *inside* the container, for the rare
case something else inside that same namespace needs port 8000.

For a tagged-image production deployment (pulling from a registry instead of
building locally), see `docker-compose.prod.yml`.

Hardware-accelerated transcoding (VAAPI/Quick Sync, or NVENC with an NVIDIA
GPU) requires passing the right device through to the backend container —
see [`docs/hardware-acceleration.md`](docs/hardware-acceleration.md) for the
device-passthrough and permissions details for each.

Both compose files also run under rootless `podman-compose`, but need a
couple of settings Docker doesn't — see
[`docs/hardware-acceleration.md`](docs/hardware-acceleration.md#podman-rootless).

### Local development

```sh
./dev.sh
```

Starts the backend (`uvicorn --reload`) on `:8100` and the frontend (Vite
dev server) on `:5273` — offset from the stock 8000/5173 ports so this can
run alongside another local project using the defaults. First run copies
`backend/.env.example` → `backend/.env` and `frontend/.env.example` →
`frontend/.env` automatically.

### Barebones (no Docker)

For running directly on the host without containers (e.g. a Raspberry Pi
you don't want to run Docker on):

```sh
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/install.sh | bash
```

Installs system dependencies, builds both services, and runs them as
systemd services. See [`deploy/README.md`](deploy/README.md) for manual
setup, updating, uninstalling, and enabling hardware-accelerated
transcoding outside a container.

## Network exposure

There is no authentication in front of the HTTP server beyond the app's own
PIN-based profile login — treat the `ports:` mapping in your compose file (or
whatever reverse proxy you put in front of it) as the real security
perimeter. Don't expose this directly to the internet without a reverse
proxy and TLS in front of it. The optional DVR SSH connection (for
retention/cleanup on a HDHomeRun DVR box) likewise does not pin host keys
(`known_hosts=None`) — same LAN-trust assumption as the HTTP calls above.

## Releasing

HDHR Open uses semantic versioning (`X.Y.Z` in `VERSION`, `backend/pyproject.toml`, and `frontend/package.json`; `vX.Y.Z` for git tags and GitHub releases). From an up-to-date `main` with a clean working tree:

```bash
./scripts/release.sh patch   # or: minor / major
git push origin main
git push origin vX.Y.Z       # printed by the script — triggers release workflows
```

The script bumps `VERSION`, `backend/pyproject.toml`, and `frontend/package.json` (regenerating `backend/uv.lock` and `frontend/package-lock.json`), then commits and tags the release locally (pass `--push` to push automatically).

Pushing the tag triggers `.github/workflows/publish-images.yml` (GHCR images for `docker-compose.prod.yml`) and `.github/workflows/release.yml` (GitHub Release with auto-generated notes).

## License

MIT — see [`LICENSE`](LICENSE).
