# Sales Reports -- unified container for the live app and /v2 rebuild.
# One image serves both by running wsgi:application under gunicorn.
#
# Installs on top of python:3.12-slim:
#   - msodbcsql18          -> required by pyodbc for on-prem SQL Server (Phase 2)
#   - unixodbc-dev         -> build-time ODBC headers for pyodbc
#   - WeasyPrint runtime   -> Cairo, Pango, GDK-PixBuf for PDF exports
#   - fonts-dejavu         -> WeasyPrint fallback font so PDFs never render blank

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

COPY webapp/requirements.txt /tmp/live-requirements.txt
COPY test/requirements.txt   /tmp/v2-requirements.txt
RUN pip install --upgrade pip \
 && pip install -r /tmp/live-requirements.txt -r /tmp/v2-requirements.txt

COPY . /app

RUN mkdir -p /app/test/outbox /app/logs /app/_report_output

ENV PORT=8000 \
    WEB_CONCURRENCY=2 \
    GUNICORN_THREADS=8 \
    GUNICORN_TIMEOUT=120 \
    USE_MOCK_DATA=true \
    MAIL_MODE=capture

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT}/v2/healthz || exit 1

# gthread worker class so a single slow request (a 25-second dashboard
# data fetch, a long polling refresh-status call) doesn't block every
# other tab's request. With 2 workers x 8 threads = 16 concurrent
# requests, which is plenty for the small user base and keeps the
# UI responsive while a refresh is in flight. The SQLite layer is
# WAL + connection-per-request, so multiple threads reading the same
# DB at once is safe.
CMD ["sh", "-c", "gunicorn --bind=0.0.0.0:${PORT} --workers=${WEB_CONCURRENCY} --worker-class=gthread --threads=${GUNICORN_THREADS} --timeout=${GUNICORN_TIMEOUT} --access-logfile=- --error-logfile=- wsgi:application"]
