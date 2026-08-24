# Build context is the repo root (not backend/) — see docker-compose.yml's
# `build.context`.
FROM python:3.12-slim

# Required for the "server_transcode" playback mode, which shells out to a
# bare `ffmpeg` on PATH (see app/api/streaming.py) — the slim base image
# doesn't ship it.
#
# va-driver-all + vainfo back the "qsv"/"vaapi" hwaccel presets in
# app/transcoding.py. Plain `ffmpeg` alone links against the VA-API/oneVPL
# *runtime* libraries (libva2/libvpl2, pulled in automatically) but ships no
# hardware driver, so h264_qsv/h264_vaapi fail at runtime ("Failed to
# initialise VAAPI connection") even though ffmpeg -encoders lists them.
# va-driver-all is architecture-aware: on amd64 it pulls intel-media-va-driver
# (Gen8+) + i965-va-driver (older Gen); on arm64 (Raspberry Pi) those two
# don't exist and it silently pulls only mesa-va-drivers instead — verified
# on both, so this is safe to add unconditionally without breaking the Pi
# build. vainfo is a tiny diagnostic binary for confirming the driver loads
# (`docker compose exec backend vainfo`) before touching the app at all.
# None of this makes hwaccel work by itself — the container also needs
# /dev/dri passed through, see the commented block in docker-compose.yml.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg va-driver-all vainfo \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY backend/app ./app

RUN uv sync --no-dev

# Runs as a fixed-UID non-root user rather than root, per container security
# best practice. /app/data is where DB_PATH/SECRET_KEY_PATH/
# HDHOMERUN_MEDIA_CACHE_DIR/RECORDINGS_DIR point in docker-compose.yml —
# pre-creating it here (owned by the app user) means Docker copies that
# ownership into the named volume the first time it's mounted, instead of
# the volume defaulting to root:root and the app being unable to write to it.
RUN groupadd --gid 1000 hdhropen \
    && useradd --uid 1000 --gid hdhropen --home-dir /app --shell /usr/sbin/nologin hdhropen \
    && mkdir -p /app/data \
    && chown -R hdhropen:hdhropen /app

COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER hdhropen

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]

# Binds all interfaces inside the container, not just localhost — required
# for Docker's port-publishing (`ports:` in compose) to reach the process at
# all, since a container's "localhost" isn't the host's. The actual exposure
# boundary is the `ports:` mapping in docker-compose.yml/.prod.yml (and
# CORS_ORIGIN for which browser origins may call it), not this bind address;
# there's no auth in front of it, so treat that mapping as the real
# perimeter — see README's "Network exposure" section.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
