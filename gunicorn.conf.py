"""Gunicorn config for the Azure App Service container.

Background-work ownership (the live email-distribution loop and v3's job
worker/scheduler) is NOT elected here anymore. post_fork runs immediately after
fork, before the worker's import path is fully set up, so starting the loop from
here was unreliable (the import could fail silently, leaving the loop running in
NO worker). Election now happens via an exclusive file lock taken from each
app's create_app/bootstrap (after imports), which is dependable:

  - live app: webapp.app._start_email_distribution_check (flock)
  - v3:       web._is_background_leader (flock)

This file is kept (and passed via --config) so future gunicorn hooks have a home.
"""

from __future__ import annotations

import logging

log = logging.getLogger("gunicorn.conf")
