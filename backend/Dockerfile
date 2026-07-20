# syntax=docker/dockerfile:1

# Single image, two workloads. Northflank runs this twice with different start
# commands — one API service, one worker service — so both always ship the
# identical dependency set and there is no chance of them drifting apart.
#
#   API     : uvicorn api:app --host 0.0.0.0 --port $PORT     (this is the default CMD)
#   Worker  : python cron_worker.py
FROM python:3.13-slim

# - PYTHONUNBUFFERED so logs reach the platform's collector immediately rather
#   than sitting in a buffer until the process exits.
# - PYTHONDONTWRITEBYTECODE keeps the layer clean; .pyc buys nothing here.
# - LOG_TO_FILE=0 because the platform captures stdout; writing cron_worker.log
#   inside a container just grows an unreachable file.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LOG_TO_FILE=0

WORKDIR /app

# curl is used by the container healthcheck. Everything else in requirements.txt
# (pandas, numpy, psycopg2-binary) ships manylinux wheels, so no compiler is
# needed and the image stays small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first: this layer is cached and only rebuilds when
# requirements.txt changes, not on every source edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run unprivileged. /app must stay writable for the worker's lock file.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Only meaningful for the API service; the worker exposes no port and the
# platform simply ignores this.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/metrics/live" > /dev/null || exit 1

# Shell form so ${PORT} injected by the platform is expanded at runtime.
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000}"]
