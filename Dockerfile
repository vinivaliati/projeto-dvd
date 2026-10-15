# syntax=docker/dockerfile:1
FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS runtime

# Media toolchain. Versions are pinned on purpose: when Debian ships a security update the
# build breaks, so every toolchain upgrade is a deliberate, reviewed commit.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        dvdauthor=0.7.2-3 \
        ffmpeg=7:7.1.5-0+deb13u1 \
        xorriso=1.5.6-1.2+b1 \
    && rm -rf /var/lib/apt/lists/*

# tsMuxeR (Blu-ray muxing) is not packaged by Debian. The release is a static binary,
# pinned by checksum.
ADD --checksum=sha256:ceaaa181ab70e201685b1e45260d337d1cbdb0aba1408d4fbc47e232a7e4c987 \
    https://github.com/justdan96/tsMuxer/releases/download/2.7.0/tsMuxer-2.7.0-linux.zip \
    /tmp/tsmuxer.zip
RUN python -I -m zipfile -e /tmp/tsmuxer.zip /usr/local/bin/ \
    && chmod 755 /usr/local/bin/tsMuxeR \
    && rm /tmp/tsmuxer.zip

COPY --from=ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 \
    /uv /usr/local/bin/uv

# Same UID/GID as the default WSL user, so files written to /work and /output belong to it.
ARG UID=1000
ARG GID=1000
RUN groupadd --gid "${GID}" app && useradd --uid "${UID}" --gid "${GID}" --create-home app \
    # The SQLite database lives in the "data" volume; a new volume copies this owner.
    && mkdir /data && chown app:app /data

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]
CMD ["uvicorn", "projeto_dvd.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

# Test stage: the runtime image plus dev dependencies and the tests, for the slow tests
# that need the real media toolchain. Never shipped.
FROM runtime AS test
USER root
RUN uv sync --frozen
COPY tests ./tests
USER app
CMD ["pytest", "-m", "slow", "--no-cov", "-p", "no:cacheprovider"]
