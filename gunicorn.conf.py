"""Gunicorn config for the Azure App Service container.

Gunicorn serves HTTP only. `supervise-web.sh` starts `web.jobs.worker_main` as a
sibling process; that process owns v3 migrations, seeds, scheduling, and durable
job polling. The live webapp email-distribution flock remains in its own app.
"""

from __future__ import annotations
