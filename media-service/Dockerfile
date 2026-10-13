# syntax=docker/dockerfile:1
# Debian trixie ships ffmpeg 7.1 - required for stable silencedetect behaviour.
ARG YTDLP_VERSION=2026.08.19
# Deno is the JS runtime yt-dlp uses for YouTube's JS challenges (EJS): without one yt-dlp 2026.08 runs the deprecated
# no-runtime path on the visionos client and warns that formats may be missing. yt-dlp requires Deno >= 2.3.0
# (wiki/EJS); pinned to a release, run with restricted permissions by yt-dlp itself (no file system, no network).
ARG DENO_VERSION=v2.9.7

FROM python:3.12-slim-trixie AS runtime
ARG YTDLP_VERSION
ARG DENO_VERSION
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp as the official standalone binary (not the pip package).
# YTDLP_VERSION=latest resolves to the newest GitHub release.
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
        amd64) asset=yt-dlp_linux ;; \
        arm64) asset=yt-dlp_linux_aarch64 ;; \
        *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    if [ "${YTDLP_VERSION}" = "latest" ]; then \
        url="https://github.com/yt-dlp/yt-dlp/releases/latest/download/${asset}"; \
    else \
        url="https://github.com/yt-dlp/yt-dlp/releases/download/${YTDLP_VERSION}/${asset}"; \
    fi; \
    curl -fsSL --retry 3 -o /usr/local/bin/yt-dlp "${url}"; \
    chmod +x /usr/local/bin/yt-dlp; \
    yt-dlp --version; \
    ffmpeg -version | head -n 1

# Deno (single static binary, ~120 MB unpacked) next to yt-dlp on PATH; yt-dlp picks it up by itself.
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
        amd64) deno_asset=deno-x86_64-unknown-linux-gnu.zip ;; \
        arm64) deno_asset=deno-aarch64-unknown-linux-gnu.zip ;; \
        *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --retry 3 -o /tmp/deno.zip "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/${deno_asset}"; \
    python3 -c "import zipfile; zipfile.ZipFile('/tmp/deno.zip').extract('deno', '/usr/local/bin')"; \
    chmod +x /usr/local/bin/deno; rm -f /tmp/deno.zip; \
    deno --version; \
    yt-dlp -v --list-impersonate-targets 2>&1 | grep 'JS runtimes'

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

# Dependencies first so app code changes do not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

ENV PATH="/app/.venv/bin:${PATH}"
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
