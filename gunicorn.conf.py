"""Gunicorn config for the Azure App Service container.

Background-work ownership (v3's job worker/scheduler) is elected from
bootstrap via an exclusive file lock (`web._is_background_leader`).

This file is kept (and passed via --config) so future gunicorn hooks have a home.
"""

from __future__ import annotations

import logging

log = logging.getLogger("gunicorn.conf")
