"""Gunicorn config for the Azure App Service container.

HTTP only. Job claiming and the scheduler run in ``python -m web.worker_main``,
started beside Gunicorn by tools/supervise-web.sh.

Access-log redaction is installed from the shared filter after the worker
loads the app (v3 is already on sys.path). create_app also installs it;
the installer skips a second copy of the same filter class.
"""


def post_worker_init(worker):  # noqa: ARG001
    try:
        from web.auth.log_redact import install_magic_link_log_redaction
    except ImportError:
        return
    install_magic_link_log_redaction()
