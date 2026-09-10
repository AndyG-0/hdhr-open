# Linux barebones (non-Docker) installation

This is the alternative to `docker compose up` described in the main
[README](../README.md) — running the backend and frontend as systemd
services directly on the host instead of in containers. Useful when you'd
rather not run Docker at all (e.g. a Raspberry Pi already used for other
things).

## One-line installation

On Debian, Ubuntu, Raspberry Pi OS, or other Debian-based distributions
(Pop!_OS, Linux Mint, Armbian, DietPi, etc.), sign in as the non-root
account that should run HDHR Open and run:

```bash
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/install.sh | bash
```

The installer requests `sudo`, installs apt-based dependencies (git,
build-essential, python3, Node.js 20, `uv`), checks out `main` to
`~/hdhr-open`, builds both backend and frontend, and enables them at boot
via systemd.

On first run, the installer interactively prompts for:
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
`/etc/systemd/journald.conf.d/`) and restart with `sudo systemctl restart
systemd-journald`.

---

## Updating

Run the standalone update script to pull the latest code, rebuild, and
restart the services — no interactive prompts, preserves your
configuration:

```bash
bash ~/hdhr-open/deploy/update.sh
```

Or as a one-liner without a local checkout:

```bash
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/update.sh | bash
```

## Uninstalling

Run the standalone uninstall script to stop and disable the systemd
services, remove the sudoers rule, and delete the installation directory:

```bash
bash ~/hdhr-open/deploy/uninstall.sh
```

Or as a one-liner without a local checkout:

```bash
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/uninstall.sh | bash
```

Or via the installer flag:

```bash
curl -fsSL https://raw.githubusercontent.com/andyg-0/hdhr-open/main/deploy/install.sh | bash -s -- --uninstall
```

#### Uninstallation options

- `--keep-data`: Removes systemd services and the sudoers entry, but
  preserves your database, `.env` files, and the rest of `~/hdhr-open`:
  ```bash
  bash ~/hdhr-open/deploy/uninstall.sh --keep-data
  ```
- `-y, --yes, --force`: Non-interactive mode (skips confirmation prompts):
  ```bash
  bash ~/hdhr-open/deploy/uninstall.sh -y
  ```

---

## Hardware acceleration (VAAPI / Quick Sync)

The installer intentionally does not install `ffmpeg` on its own — it comes
in with `apt-get install ffmpeg` the first time you need
`server_transcode` playback:

```bash
sudo apt install -y ffmpeg
```

For the `qsv`/`vaapi`/`vaapi_full` hardware-acceleration presets (see
[`docs/hardware-acceleration.md`](../docs/hardware-acceleration.md)), also
install a VA-API driver — plain `ffmpeg` links against the VA-API/oneVPL
runtime libraries but ships no hardware driver on its own:

```bash
sudo apt install -y va-driver-all vainfo
```

`vainfo` should then list your GPU's supported profiles instead of
erroring.

The backend service unit is sandboxed (`NoNewPrivileges=true`,
`ProtectSystem=strict`, an empty `CapabilityBoundingSet`) and, by default,
cannot open a GPU render node: the sandbox hides `/dev/dri`, and the
`hdhr-open` service user isn't in the host's `render` group. Both have to
be granted explicitly. Add a drop-in:

```bash
sudo systemctl edit hdhr-open-backend
```

```ini
[Service]
# Expose just the render nodes, not all of /dev.
DeviceAllow=/dev/dri/renderD128 rw
DeviceAllow=/dev/dri/renderD129 rw
SupplementaryGroups=render
```

Then `sudo systemctl restart hdhr-open-backend`. Verify with **Settings →
playback → Run diagnostics**, which reports the process's groups, each
render node's permissions, the loaded driver, and a real test encode
through every preset. Note the render node isn't always `renderD128` — a
second DRM device shifts the iGPU to `renderD129`; the diagnostics list
what's present, and the playback settings' **Render device** field selects
it.

## Hardware acceleration (NVIDIA / NVENC)

Stock Debian/Ubuntu `ffmpeg` has no `h264_nvenc` encoder compiled in —
NVIDIA's encode headers are proprietary/nonfree, so Debian's mainline build
excludes them (this is the same reason the backend *container* image swaps
in `jellyfin-ffmpeg`; see `docs/hardware-acceleration.md`). Do the same on
bare metal: install [`jellyfin-ffmpeg`](https://github.com/jellyfin/jellyfin-ffmpeg)
instead of stock `ffmpeg`, and put it ahead of `/usr/bin` on `PATH` (or
symlink it over `/usr/local/bin/ffmpeg`/`ffprobe`, which the backend unit's
`PATH` already prefers):

```bash
sudo apt install -y curl gnupg
curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/jellyfin.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/jellyfin.gpg] https://repo.jellyfin.org/debian $(source /etc/os-release && echo "$VERSION_CODENAME") main" | sudo tee /etc/apt/sources.list.d/jellyfin.list
sudo apt update
sudo apt install -y jellyfin-ffmpeg7
sudo ln -sf /usr/lib/jellyfin-ffmpeg/ffmpeg /usr/local/bin/ffmpeg
sudo ln -sf /usr/lib/jellyfin-ffmpeg/ffprobe /usr/local/bin/ffprobe
```

Also make sure current NVIDIA drivers are installed on the host
(`nvidia-smi` should succeed). Then grant the sandboxed backend unit access
to the GPU devices:

```bash
sudo systemctl edit hdhr-open-backend
```

```ini
[Service]
DeviceAllow=/dev/nvidia0 rw
DeviceAllow=/dev/nvidiactl rw
DeviceAllow=/dev/nvidia-uvm rw
SupplementaryGroups=video
```

Then `sudo systemctl restart hdhr-open-backend`, set the playback settings'
hwaccel to `nvenc`, and confirm with **Run diagnostics** as above.

## Manual setup

The installer is the supported path. These notes are for a manually
checked-out tree or custom service setup.

Testing `server_transcode` locally on macOS instead needs Homebrew's build:

```bash
brew install ffmpeg
```

### Configure

- `backend/.env` — copy from `backend/.env.example`; set `TIMEZONE` and
  `CORS_ORIGIN` at minimum. Everything else (Schedules Direct credentials,
  DVR settings, etc.) is configured through the web UI after first boot.
- `frontend/.env` — copy from `frontend/.env.example`; set
  `PUBLIC_API_BASE_URL` (usually `http://localhost:8000` if both services
  run on the same host, or the host's LAN IP otherwise).

### Build

```bash
cd backend && uv sync
cd ../frontend && npm install && npm run build
```

### Install systemd services

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
instance of this unit against a given `storage.db` — see the main README's
"Network exposure" section for why (single SQLite writer, not a
multi-process design).

## Docker (alternative to native services)

Instead of building with `uv`/`npm` and installing systemd units, use
`docker compose up -d --build` as described in the main README — see there
and in `docs/hardware-acceleration.md` for the containerized equivalent of
the hwaccel steps above.
