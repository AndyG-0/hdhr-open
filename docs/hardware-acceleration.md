# Hardware-Accelerated Transcoding

`server_transcode` playback (Settings → playback) shells out to `ffmpeg` to
convert the tuner's raw MPEG-2 ATSC OTA stream into browser-playable
H.264/AAC. Software encoding (the `software`/`software_lowpower` presets)
works everywhere but costs real CPU per concurrent viewer; the presets below
offload the encode to a GPU instead. See `backend/app/transcoding.py` for the
exact ffmpeg arguments each preset builds.

| Preset | Hardware | Platform |
|---|---|---|
| `software` | Any CPU | Any — default, safest fallback |
| `software_lowpower` | Any CPU | Tuned for Raspberry Pi / weak ARM SBCs |
| `vaapi` | Intel iGPU or AMD GPU | Linux |
| `vaapi_full` | Intel iGPU or AMD GPU (decode + encode) | Linux |
| `qsv` | Intel Quick Sync | Linux |
| `nvenc` | NVIDIA GPU | Linux |
| `videotoolbox` | Apple Silicon / Intel Mac | macOS only — not available in a Linux container |

Whichever path you're on, **Settings → playback → Run diagnostics** is the
way to confirm it actually works: it reports the process's groups, each
render node's permissions, the loaded driver, and a real test encode through
every preset (`backend/app/hwaccel.py`).

## Docker — Intel/AMD (VAAPI, Quick Sync)

The backend image already bundles the VAAPI/QSV driver packages
(`va-driver-all`, `vainfo` — see `backend/Dockerfile`); a container just has
no access to host devices until one is passed through. Uncomment the
`devices:`/`group_add:` block under the `backend` service in
`docker-compose.yml` (or `docker-compose.prod.yml`):

```yaml
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - "${RENDER_GID:-108}"
```

Find your host's actual render-group GID with `getent group render`, then
run e.g. `RENDER_GID=108 docker compose up -d`. Two things that commonly
need adjusting after that, both surfaced by the in-app diagnostics:

- The render node isn't always `renderD128` — a second DRM device (a
  discrete GPU, or a `simpledrm`/`vkms` node) shifts the iGPU to
  `renderD129`; set the widget's **Render device** setting to match.
- Some Intel setups need the driver named explicitly — if `vainfo` reports
  no driver, add `LIBVA_DRIVER_NAME=iHD` (Intel Gen8+), `i965` (older
  Intel), or `radeonsi` (AMD) to the backend service's `environment:`.

## Docker — NVIDIA (NVENC)

Unlike VAAPI/QSV, this needs one extra piece: Debian's stock `ffmpeg`
package has no `h264_nvenc` encoder compiled in (NVIDIA's encode headers are
proprietary/nonfree, so Debian's build excludes them). The backend image
works around this by installing
[`jellyfin-ffmpeg`](https://github.com/jellyfin/jellyfin-ffmpeg) on amd64
builds, which does ship `h264_nvenc`.

1. Install the [NVIDIA Container
   Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
   on the Docker host, then point Docker at it and restart:
   ```bash
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```
2. Uncomment the NVIDIA block under the `backend` service in
   `docker-compose.yml` (or `.prod.yml`) — instead of, not in addition to,
   the `/dev/dri` block above:
   ```yaml
       environment:
         - NVIDIA_DRIVER_CAPABILITIES=compute,video,utility
     deploy:
       resources:
         reservations:
           devices:
             - driver: nvidia
               count: 1
               capabilities: [gpu]
   ```
   The `NVIDIA_DRIVER_CAPABILITIES` line matters as much as the device
   reservation: the toolkit's default capability set (`compute,utility`)
   does not inject `libnvidia-encode.so` into the container, and
   `h264_nvenc` fails to load even with the GPU otherwise visible.
3. This does **not** need Swarm mode — `docker compose up` (Compose V2)
   honors `deploy.resources.reservations` directly.
4. Set the widget's `hwaccel` setting to `nvenc` and confirm with **Run
   diagnostics**.

## Barebones (non-Docker) install

Running directly on the host has the same two requirements, just satisfied
differently — see [`deploy/README.md`](../deploy/README.md#hardware-acceleration)
for the full walkthrough: installing `ffmpeg`/`va-driver-all`/`vainfo` (or
`jellyfin-ffmpeg` for NVENC) on the host, and the systemd `DeviceAllow=`/
`SupplementaryGroups=` drop-in needed because the installed service is
sandboxed by default.

## Apple VideoToolbox

Only reachable when the backend process itself runs on macOS — not
possible in a Linux container, and not relevant to the Docker or systemd
paths above. Useful mainly for local development on a Mac
(`./dev.sh`, or the "Manual setup" section of `deploy/README.md`).
