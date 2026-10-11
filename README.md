# HDHR Open

[![CI](https://github.com/AndyG-0/hdhr-open/actions/workflows/ci.yml/badge.svg)](https://github.com/AndyG-0/hdhr-open/actions/workflows/ci.yml)
[![CodeQL](https://github.com/AndyG-0/hdhr-open/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/AndyG-0/hdhr-open/security/code-scanning)
[![License: MIT](https://img.shields.io/github/license/AndyG-0/hdhr-open)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/AndyG-0/hdhr-open)](https://github.com/AndyG-0/hdhr-open/releases/latest)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-donate-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/andyg0)

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
- **Live playback controls** — a Go Live button returns to the live edge of
  an in-progress channel or recording, with live-edge join, a playback stats
  panel, and automatic quality downgrade for single-viewer live TV.
- **Commercial detection** — comskip marks commercial breaks in completed
  recordings (Built-in DVR, and HDHomeRun DVR once its storage is mounted),
  with an opt-in auto-skip in the player. See the
  [DVR Guide](https://andyg-0.github.io/hdhr-open/dvr/#commercial-detection).
- **Optional hardware-accelerated transcoding** — VAAPI/Quick Sync support
  with a built-in diagnostics page (Settings → playback) to verify the
  container actually has GPU access before relying on it.
- **DVR** — dual-engine recording support with either HDHR Open's Built-in
  self-hosted DVR or SiliconDust's official HDHomeRun DVR engine. Supports
  cross-provider Series ID enrichment (matching XMLTV airings against
  HDHomeRun Cloud) and automatic fallback with user notifications when a Series
  ID cannot be resolved. Browse in-progress and completed recordings, and seek
  within recordings in `server_transcode` mode. See the
  [DVR Guide](https://andyg-0.github.io/hdhr-open/dvr/) for details on guide
  matching, Series IDs, and fallback behavior.
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

📖 **Full install, config, and usage docs: <https://andyg-0.github.io/hdhr-open/>**

### Docker (recommended for self-hosting)

```sh
cp backend/.env.example backend/.env   # edit if you need to
docker compose up -d --build
```

This starts the backend on `:8000` and the frontend on `:3000`. Open
`http://<host>:3000` in a browser, or the host's LAN IP on the same network.
See the [Installation guide](https://andyg-0.github.io/hdhr-open/installation/)
for port overrides, production/tagged images, Podman, and the
[Configuration guide](https://andyg-0.github.io/hdhr-open/configuration/) for
every environment variable, including `RECORDINGS_PATH` and
`HDHOMERUN_RECORDINGS_PATH`.

Hardware-accelerated transcoding (VAAPI/Quick Sync, or NVENC with an NVIDIA
GPU) requires passing the right device through to the backend container —
see [Hardware Acceleration](https://andyg-0.github.io/hdhr-open/hardware-acceleration/).

### Local development

```sh
./dev.sh
```

Starts the backend on `:8100` and the frontend on `:5273`. See
[`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md) for details.

### Barebones (no Docker)

For running directly on the host without containers (e.g. a Raspberry Pi
you don't want to run Docker on):

```sh
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/install.sh | bash
```

Installs system dependencies, builds both services, and runs them as
systemd services. See the
[Installation guide](https://andyg-0.github.io/hdhr-open/installation/#barebones-no-docker)
for manual setup and hardware acceleration, and
[Updating & Uninstalling](https://andyg-0.github.io/hdhr-open/updating/).

## Network exposure

There is no authentication in front of the HTTP server beyond the app's own
PIN-based profile login — treat the `ports:` mapping in your compose file (or
whatever reverse proxy you put in front of it) as the real security
perimeter. See
[Configuration → Network exposure](https://andyg-0.github.io/hdhr-open/configuration/#network-exposure)
for the full picture.

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
