# python:3.12.13-slim-bookworm, multi-arch index digest
FROM python:3.15.1-slim-bookworm@sha256:575f8bc12ec26542e0678bc6b60e385218248019d433157ec327264a78c3a853

# uv 0.13.1, multi-arch index digest. Matches the uv version used to lock the API.
COPY --from=ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_NO_SYNC=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    CACHE_PATH=/var/lib/osu-score-api/cache \
    STATS_PATH=/var/lib/osu-score-api/stats/usage.json

WORKDIR /app

RUN useradd --system --uid 10001 --create-home --home-dir /home/osu osu \
    && mkdir -p /var/lib/osu-score-api/cache /var/lib/osu-score-api/stats \
    && chown -R osu:osu /var/lib/osu-score-api

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# The entrypoint starts as root to prepare the data volume, then drops to user osu.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--proxy-headers"]
