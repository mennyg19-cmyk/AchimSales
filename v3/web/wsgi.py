"""WSGI entrypoint for gunicorn: `gunicorn web.wsgi:application`."""

from __future__ import annotations

from web import create_app

application = create_app()
