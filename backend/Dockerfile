# Build context is the repo root (not backend/) — see docker-compose.yml's
# `build.context`.

# --- ccextractor builder stage ---------------------------------------------
#
# CC-8/CC-9: live caption extraction (media_cache.py's
# _run_live_caption_ccextractor_process) shells out to `ccextractor` for its
# near-zero-latency real-time stream decode (see TODO.md CC-8) — ffmpeg's own
# movie/subcc decode path, used only for finished-recording caption
# generation, stays on the `ffmpeg` installed below and needs none of this.
#
# ccextractor isn't in Debian bookworm's apt repos (only bullseye/oldstable
# and sid/unstable) and ships no official arm64 Linux binary (Raspberry Pi is
# a real target here, see the va-driver-all comment below), so it's built
# from source here — a near-verbatim port of ccextractor's own
# BUILD_TYPE=minimal recipe (docker/Dockerfile in
# github.com/CCExtractor/ccextractor, fetched and read directly rather than
# guessed at), pinned to release v0.96.6 rather than `master` for
# reproducibility. `minimal` means no OCR/hardsubx (burned-in subtitle OCR)
# support, since this only ever needs stream-mode CEA-608/708 byte decode —
# it still vendors several thirdparty libs as source (zlib/libpng/freetype/
# utf8proc) rather than linking system packages, same as the reference
# recipe; only libgpac is linked as a shared lib. Deviating from that
# reference file is how this stage rots quietly, so keep it in sync if
# ccextractor's own build system changes.
FROM debian:bookworm-slim AS ccextractor-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git curl ca-certificates gcc g++ cmake make pkg-config bash \
        zlib1g-dev libpng-dev libjpeg-dev libssl-dev libfreetype-dev \
        libxml2-dev libcurl4-gnutls-dev clang libclang-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR /root
RUN git clone --depth 1 --branch v0.96.6 https://github.com/CCExtractor/ccextractor.git

# GPAC v2.4.0, built as a shared lib only — ccextractor links against
# libgpac for container demuxing.
RUN git clone --depth 1 --branch v2.4.0 https://github.com/gpac/gpac
WORKDIR /root/gpac
RUN ./configure && make -j"$(nproc)" lib && make install-lib && ldconfig
WORKDIR /root
RUN rm -rf /root/gpac

WORKDIR /root/ccextractor/linux

# Generates version-info headers ccextractor.c expects (VERSION_FILE_PRESENT
# below) — skipping this step produces a binary that fails to compile.
RUN ./pre-build.sh

RUN cd ../src/rust && CARGO_TARGET_DIR=../../linux/rust cargo build --release
RUN cp rust/release/libccx_rust.a ./libccx_rust.a

# Exact BUILD_TYPE=minimal flags/include/source-list/linker args from
# ccextractor's docker/Dockerfile — no OCR/hardsubx, so no tesseract/
# leptonica/ffmpeg-dev build deps are needed at all.
RUN BLD_FLAGS="-std=gnu99 -Wno-write-strings -Wno-pointer-sign -D_FILE_OFFSET_BITS=64 -DVERSION_FILE_PRESENT -DFT2_BUILD_LIBRARY -DGPAC_DISABLE_VTT -DGPAC_DISABLE_OD_DUMP -DGPAC_DISABLE_REMOTERY -DNO_GZIP -DGPAC_64_BITS" && \
    BLD_INCLUDE="-I../src -I../src/lib_ccx/ -I /usr/include/gpac/ -I../src/thirdparty/libpng -I../src/thirdparty/zlib -I../src/lib_ccx/zvbi -I../src/thirdparty/lib_hash -I../src/thirdparty -I../src/thirdparty/freetype/include" && \
    BLD_LINKER="-lm -Wl,--allow-multiple-definition -lpthread -ldl -lgpac ./libccx_rust.a" && \
    SRC_LIBPNG="$(find ../src/thirdparty/libpng/ -name '*.c')" && \
    SRC_ZLIB="$(find ../src/thirdparty/zlib/ -name '*.c')" && \
    SRC_CCX="$(find ../src/lib_ccx/ -name '*.c')" && \
    SRC_GPAC="$(find /usr/include/gpac/ -name '*.c' 2>/dev/null || true)" && \
    SRC_HASH="$(find ../src/thirdparty/lib_hash/ -name '*.c')" && \
    SRC_UTF8PROC="../src/thirdparty/utf8proc/utf8proc.c" && \
    SRC_FREETYPE="../src/thirdparty/freetype/autofit/autofit.c \
        ../src/thirdparty/freetype/base/ftbase.c \
        ../src/thirdparty/freetype/base/ftbbox.c \
        ../src/thirdparty/freetype/base/ftbdf.c \
        ../src/thirdparty/freetype/base/ftbitmap.c \
        ../src/thirdparty/freetype/base/ftcid.c \
        ../src/thirdparty/freetype/base/ftfntfmt.c \
        ../src/thirdparty/freetype/base/ftfstype.c \
        ../src/thirdparty/freetype/base/ftgasp.c \
        ../src/thirdparty/freetype/base/ftglyph.c \
        ../src/thirdparty/freetype/base/ftgxval.c \
        ../src/thirdparty/freetype/base/ftinit.c \
        ../src/thirdparty/freetype/base/ftlcdfil.c \
        ../src/thirdparty/freetype/base/ftmm.c \
        ../src/thirdparty/freetype/base/ftotval.c \
        ../src/thirdparty/freetype/base/ftpatent.c \
        ../src/thirdparty/freetype/base/ftpfr.c \
        ../src/thirdparty/freetype/base/ftstroke.c \
        ../src/thirdparty/freetype/base/ftsynth.c \
        ../src/thirdparty/freetype/base/ftsystem.c \
        ../src/thirdparty/freetype/base/fttype1.c \
        ../src/thirdparty/freetype/base/ftwinfnt.c \
        ../src/thirdparty/freetype/bdf/bdf.c \
        ../src/thirdparty/freetype/bzip2/ftbzip2.c \
        ../src/thirdparty/freetype/cache/ftcache.c \
        ../src/thirdparty/freetype/cff/cff.c \
        ../src/thirdparty/freetype/cid/type1cid.c \
        ../src/thirdparty/freetype/gzip/ftgzip.c \
        ../src/thirdparty/freetype/lzw/ftlzw.c \
        ../src/thirdparty/freetype/pcf/pcf.c \
        ../src/thirdparty/freetype/pfr/pfr.c \
        ../src/thirdparty/freetype/psaux/psaux.c \
        ../src/thirdparty/freetype/pshinter/pshinter.c \
        ../src/thirdparty/freetype/psnames/psnames.c \
        ../src/thirdparty/freetype/raster/raster.c \
        ../src/thirdparty/freetype/sfnt/sfnt.c \
        ../src/thirdparty/freetype/smooth/smooth.c \
        ../src/thirdparty/freetype/truetype/truetype.c \
        ../src/thirdparty/freetype/type1/type1.c \
        ../src/thirdparty/freetype/type42/type42.c \
        ../src/thirdparty/freetype/winfonts/winfnt.c" && \
    BLD_SOURCES="../src/ccextractor.c $SRC_CCX $SRC_GPAC $SRC_ZLIB $SRC_LIBPNG $SRC_HASH $SRC_UTF8PROC $SRC_FREETYPE" && \
    gcc $BLD_FLAGS $BLD_INCLUDE -o ccextractor $BLD_SOURCES $BLD_LINKER

# --- runtime image -----------------------------------------------------------
# Pinned to bookworm (not the floating "slim" tag) so this stays on the same
# Debian release as the jellyfin-ffmpeg7 apt repo below — "slim" has drifted
# to trixie, whose libvpx7/libx265-199 don't satisfy jellyfin's bookworm .deb.
FROM python:3.14-slim-bookworm

# Set by buildx automatically (also honored by plain `docker build`/`docker
# compose build` under BuildKit, the default since Docker 23) — used below to
# skip the amd64-only jellyfin-ffmpeg install on arm64/Raspberry Pi builds.
ARG TARGETARCH

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

# --- jellyfin-ffmpeg (amd64 only): unlocks the "nvenc" hwaccel preset ------
#
# Debian's own `ffmpeg` package (installed above) has no h264_nvenc encoder
# compiled in: NVIDIA's encode SDK headers (nv-codec-headers) are
# proprietary/nonfree, so Debian's mainline ffmpeg build excludes them
# entirely — unlike va-driver-all above, this isn't a missing driver
# package, it's a build-time exclusion in ffmpeg itself. jellyfin-ffmpeg
# ships a build with nvenc (and vaapi/qsv, same as above) compiled in, so
# swap it in for amd64 builds only — NVIDIA GPUs aren't an arm64/Raspberry
# Pi scenario, and jellyfin-ffmpeg's arm64 packages have historically
# lagged behind amd64 for a given Debian codename. Symlinking over
# /usr/local/bin means every existing `subprocess` call to bare
# "ffmpeg"/"ffprobe" (app/api/streaming.py, app/api/dvr_streaming.py,
# app/hwaccel.py, ...) picks it up with no code changes.
#
# This does NOT bundle the NVIDIA driver itself — libnvidia-encode.so still
# has to come from the host at container-runtime via the NVIDIA Container
# Toolkit (see the commented `deploy:`/`environment:` block in
# docker-compose.yml and docs/hardware-acceleration.md).
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends curl gnupg \
        && curl -fsSL https://repo.jellyfin.org/jellyfin_team.gpg.key | gpg --dearmor -o /usr/share/keyrings/jellyfin.gpg \
        && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/jellyfin.gpg] https://repo.jellyfin.org/debian bookworm main" > /etc/apt/sources.list.d/jellyfin.list \
        && apt-get update \
        && apt-get install -y --no-install-recommends jellyfin-ffmpeg7 \
        && ln -sf /usr/lib/jellyfin-ffmpeg/ffmpeg /usr/local/bin/ffmpeg \
        && ln -sf /usr/lib/jellyfin-ffmpeg/ffprobe /usr/local/bin/ffprobe \
        && apt-get purge -y curl gnupg \
        && apt-get autoremove -y \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# ccextractor's own runtime shared-lib deps for a BUILD_TYPE=minimal build
# (docker/Dockerfile's `final` stage) — libgpac itself comes from the
# builder stage below since it's not an apt package.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpng16-16 libjpeg62-turbo zlib1g libssl3 libcurl4 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ccextractor-builder /usr/local/lib/libgpac.so* /usr/local/lib/
RUN ldconfig
COPY --from=ccextractor-builder /root/ccextractor/linux/ccextractor /usr/local/bin/ccextractor

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
#
# UVICORN_PORT overrides the port uvicorn actually binds to inside the
# container (default 8000) — see docker-compose.yml/.prod.yml, which map
# this to the host via BACKEND_PORT. Shell form (not exec form) so
# ${UVICORN_PORT} is expanded at container start, not build time.
ENV UVICORN_PORT=8000
CMD ["sh", "-c", "exec uv run uvicorn app.main:app --host 0.0.0.0 --port ${UVICORN_PORT}"]
