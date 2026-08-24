# HDHR Open — backend

FastAPI backend for HDHR Open. No ORM — raw `sqlite3` (see
`app/storage/db.py`). Single household, single tuner per deployment.

See the [root README](../README.md) for what this project is and how to run
it via Docker. This file covers backend-specific local development.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management
- `ffmpeg` on `PATH` — required for `server_transcode` playback mode and for
  generating recording thumbnails/captions. Not needed if you only use
  `external` playback mode.

## Setup

```sh
cp .env.example .env   # edit as needed — see comments in .env.example
uv sync
uv run uvicorn app.main:app --reload
```

The server listens on `:8000` by default. See `.env.example` for every
setting the app reads (`TIMEZONE`, `CORS_ORIGIN`, cookie flags, `LOG_LEVEL`,
and the storage paths `DB_PATH` / `SECRET_KEY_PATH` /
`HDHOMERUN_MEDIA_CACHE_DIR` / `RECORDINGS_DIR`, which are normally left at
their local-dev defaults and only overridden by `docker-compose.yml` to
point into a mounted volume).

## Tests

```sh
uv run pytest
```

## Layout

- `app/api/` — route handlers, one module per resource (`tuner`, `guide`,
  `dvr`, `streaming`, `network_settings`, `settings`, `devices`, `users`,
  `setup`, `admin`).
- `app/integrations/hdhomerun_client.py` — client for the local tuner's HTTP
  API and SiliconDust's cloud guide/DVR API.
- `app/storage/` — `db.py` (schema + queries), `cache.py` (in-process
  caching for guide/tuner responses).
- `app/dvr/media_cache.py` — generates and caches WebVTT captions and
  scrub-bar thumbnail sprites for completed recordings.
- `app/auth.py` — PIN-based profile login, device/session cookies.
- `app/crypto.py` — encrypts secret values (e.g. HDHomeRun DVR key) stored in
  `network_integrations` at rest.
- `app/transcoding.py` / `app/hwaccel.py` — ffmpeg command construction and
  hardware-acceleration (VAAPI/Quick Sync) detection + diagnostics.
- `app/scheduler.py` — shared APScheduler instance. Currently starts with no
  registered jobs; guide-refresh and self-hosted-recording jobs will
  register against it as those land (see the root `ROADMAP.md`).
