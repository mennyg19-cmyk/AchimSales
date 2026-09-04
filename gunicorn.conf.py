"""Gunicorn config for the Azure App Service container.

Gunicorn serves HTTP only. `supervise-web.sh` starts `web.jobs.worker_main` as a
sibling process; that process owns v3 migrations, seeds, scheduling, and durable
job polling. The live `/legacy` email-distribution flock remains in-process this slice.

ponytail: keep --config so .gitattributes LF pin and Azure invocation stay;
no post_fork hooks until a real hook is required.
"""

from __future__ import annotations
