# Hardware-Accelerated Transcoding

`server_transcode` playback (Settings → Recording) shells out to `ffmpeg` to
convert the tuner's raw MPEG-2 ATSC OTA stream into browser-playable
H.264/AAC. Software encoding (the `software`/`software_lowpower` presets)
works everywhere but costs real CPU per concurrent viewer; the presets below
offload the encode to a GPU instead.

| Preset | Hardware | Platform |
|---|---|---|
| `software` | Any CPU | Any — default, safest fallback |
| `software_lowpower` | Any CPU | Tuned for Raspberry Pi / weak ARM SBCs |
| `vaapi` | Intel iGPU or AMD GPU | Linux |
| `vaapi_full` | Intel iGPU or AMD GPU (decode + encode) | Linux |
| `qsv` | Intel Quick Sync | Linux |
| `nvenc` | NVIDIA GPU | Linux |
| `videotoolbox` | Apple Silicon / Intel Mac | macOS only — not available in a Linux container |

Whichever path you're on, **Settings → Recording → Run diagnostics** is the
way to confirm it actually works: it reports the process's groups, each
render node's permissions, the loaded driver, and a real test encode through
every preset.

## Docker

The backend image already bundles the VAAPI/QSV driver packages
(`va-driver-all`, `vainfo`) and, on amd64, `jellyfin-ffmpeg` for NVENC — a
container just has no access to host devices until one is passed through.

=== "Intel/AMD (VAAPI, Quick Sync)"

    Uncomment the `devices:`/`group_add:` block under the `backend` service
    in `docker-compose.yml` (or `docker-compose.prod.yml`):

    ```yaml
        devices:
          - /dev/dri:/dev/dri
        group_add:
          - "${RENDER_GID:-108}"
    ```

    Find your host's actual render-group GID with `getent group render`,
    then run e.g. `RENDER_GID=108 docker compose up -d`. Two things that
    commonly need adjusting after that, both surfaced by the in-app
    diagnostics:

    - The render node isn't always `renderD128` — a second DRM device (a
      discrete GPU, or a `simpledrm`/`vkms` node) shifts the iGPU to
      `renderD129`; set the widget's **Render device** setting to match.
    - Some Intel setups need the driver named explicitly — if `vainfo`
      reports no driver, add `LIBVA_DRIVER_NAME=iHD` (Intel Gen8+), `i965`
      (older Intel), or `radeonsi` (AMD) to the backend service's
      `environment:`.

=== "NVIDIA (NVENC)"

    Unlike VAAPI/QSV, this needs one extra piece: Debian's stock `ffmpeg`
    package has no `h264_nvenc` encoder compiled in (NVIDIA's encode
    headers are proprietary/nonfree, so Debian's build excludes them). The
    backend image works around this by installing
    [`jellyfin-ffmpeg`](https://github.com/jellyfin/jellyfin-ffmpeg) on
    amd64 builds, which does ship `h264_nvenc`.

    1. Install the [NVIDIA Container
       Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
       on the Docker host, then point Docker at it and restart:
       ```bash
       sudo nvidia-ctk runtime configure --runtime=docker
       sudo systemctl restart docker
       ```
    2. Uncomment the NVIDIA block under the `backend` service in
       `docker-compose.yml` (or `.prod.yml`) — instead of, not in addition
       to, the `/dev/dri` block above:
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
       reservation: the toolkit's default capability set
       (`compute,utility`) does not inject `libnvidia-encode.so` into the
       container, and `h264_nvenc` fails to load even with the GPU
       otherwise visible.
    3. This does **not** need Swarm mode — `docker compose up` (Compose V2)
       honors `deploy.resources.reservations` directly.
    4. Set the widget's `hwaccel` setting to `nvenc` and confirm with **Run
       diagnostics**.

=== "Podman (rootless)"

    <span id="podman-rootless"></span>

    The `docker-compose.yml`/`.prod.yml` files also run under
    `podman-compose`, but rootless Podman needs a few settings that plain
    Docker doesn't — they're present in both files as no-ops (ignored by
    Docker) or comments (opt-in), never active by default:

    - **`x-podman: in_pod: false`** (top-level, active by default) —
      Podman Compose normally puts every service in one shared pod. That's
      harmless on its own, but it conflicts with `userns_mode: keep-id`
      below (Podman rejects `--userns` combined with `--pod`), so it's
      disabled project-wide. Services still reach each other fine over
      published ports/LAN addresses, not pod-shared localhost, so nothing
      else changes.
    - **`userns_mode: keep-id`** (commented under `backend`) — the backend
      container runs as a fixed uid/gid 1000 (`hdhropen`). Under Docker
      (rootful or rootless), that's stable. Under *rootless Podman*
      without this setting, container uid 1000 is remapped into the subuid
      range instead — it isn't the invoking host user at all, which breaks
      both writing to a host-owned `CONFIG_PATH`/`RECORDINGS_PATH`
      directory and opening `/dev/dri`. `keep-id` maps the invoking host
      user's own uid/gid into the container as 1000, matching `hdhropen`
      exactly. Uncomment it any time you're deploying with Podman instead
      of Docker, even without hardware acceleration.
    - **`group_add: [keep-groups]`** (commented under `backend`,
      alternative to the numeric `group_add: ["${RENDER_GID:-108}"]`
      above it) — once `keep-id` is active, the numeric-GID trick used for
      Docker GPU passthrough stops working: that GID was never part of the
      user-namespace mapping to begin with. `keep-groups` is Podman's
      dedicated escape hatch — it passes the invoking host user's actual
      supplementary groups (e.g. `render`) straight into the container
      process. It requires the `crun` runtime (Podman's default) and is
      exclusive: don't combine it with any other `group_add` entry.

## Barebones (no Docker)

Running directly on the host has the same requirements as Docker, just
satisfied differently: the installer intentionally does not install
`ffmpeg` on its own — it comes in with `apt-get install ffmpeg` the first
time you need `server_transcode` playback:

```bash
sudo apt install -y ffmpeg
```

The backend service unit is sandboxed (`NoNewPrivileges=true`,
`ProtectSystem=strict`, an empty `CapabilityBoundingSet`) and, by default,
cannot open a GPU device: the sandbox hides it, and the service user isn't
in the relevant host group. Both have to be granted explicitly, per preset
below.

=== "VAAPI / Quick Sync"

    For the `qsv`/`vaapi`/`vaapi_full` presets, install a VA-API driver —
    plain `ffmpeg` links against the VA-API/oneVPL runtime libraries but
    ships no hardware driver on its own:

    ```bash
    sudo apt install -y va-driver-all vainfo
    ```

    `vainfo` should then list your GPU's supported profiles instead of
    erroring.

    The sandboxed unit hides `/dev/dri` and the `hdhr-open` service user
    isn't in the host's `render` group by default. Add a drop-in:

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

    Then `sudo systemctl restart hdhr-open-backend`. Verify with
    **Settings → Recording → Run diagnostics**, which reports the
    process's groups, each render node's permissions, the loaded driver,
    and a real test encode through every preset. Note the render node
    isn't always `renderD128` — a second DRM device shifts the iGPU to
    `renderD129`; the diagnostics list what's present, and the playback
    settings' **Render device** field selects it.

=== "NVIDIA (NVENC)"

    Stock Debian/Ubuntu `ffmpeg` has no `h264_nvenc` encoder compiled in —
    NVIDIA's encode headers are proprietary/nonfree, so Debian's mainline
    build excludes them (the same reason the backend *container* image
    swaps in `jellyfin-ffmpeg` above). Do the same on bare metal: install
    [`jellyfin-ffmpeg`](https://github.com/jellyfin/jellyfin-ffmpeg)
    instead of stock `ffmpeg`, and put it ahead of `/usr/bin` on `PATH`
    (or symlink it over `/usr/local/bin/ffmpeg`/`ffprobe`, which the
    backend unit's `PATH` already prefers):

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
    (`nvidia-smi` should succeed). Then grant the sandboxed backend unit
    access to the GPU devices:

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

    Then `sudo systemctl restart hdhr-open-backend`, set the playback
    settings' hwaccel to `nvenc`, and confirm with **Run diagnostics** as
    above.

## Apple VideoToolbox

Only reachable when the backend process itself runs on macOS — not
possible in a Linux container, and not relevant to the Docker or systemd
paths above. Useful mainly for local development on a Mac (`./dev.sh`),
where plain Homebrew `ffmpeg` (`brew install ffmpeg`) is enough.
