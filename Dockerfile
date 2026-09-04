# Sales Reports container image. Azure App Service currently uses startup.sh,
# not this Dockerfile; keep its runtime dependencies in sync with the lock.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    ACCEPT_EULA=Y

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg apt-transport-https \
        build-essential \
        unixodbc-dev \
        libcairo2 libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info \
        fonts-dejavu \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
      > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends msodbcsql18 \
 && apt-get purge -y --auto-remove build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# webapp/requirements.txt already covers live + v3 (+ rebuild shares the same stack).
COPY webapp/requirements.txt /tmp/live-requirements.txt
RUN pip install --upgrade pip \
 && pip install --require-hashes -r /tmp/live-requirements.txt

COPY . /app

RUN mkdir -p /app/logs /app/_report_output

ENV PORT=8000 \
    WEB_CONCURRENCY=2 \
    GUNICORN_THREADS=8 \
    GUNICORN_TIMEOUT=120 \
    USE_MOCK_DATA=true \
    MAIL_MODE=capture

EXPOSE 8000

# Prefer v3's cheap /test/healthz when mounted; otherwise accept live / (login redirect).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT}/test/healthz \
     || curl -fsS -o /dev/null http://127.0.0.1:${PORT}/ \
     || exit 1

# gthread worker class so a single slow request (a 25-second dashboard
# data fetch, a long polling refresh-status call) doesn't block every
# other tab's request. With 2 workers x 8 threads = 16 concurrent
# requests, which is plenty for the small user base and keeps the
# UI responsive while a refresh is in flight. The SQLite layer is
# WAL + connection-per-request, so multiple threads reading the same
# DB at once is safe.
CMD ["sh", "-c", "gunicorn --bind=0.0.0.0:${PORT} --workers=${WEB_CONCURRENCY} --worker-class=gthread --threads=${GUNICORN_THREADS} --timeout=${GUNICORN_TIMEOUT} --access-logfile=- --error-logfile=- wsgi:application"]
