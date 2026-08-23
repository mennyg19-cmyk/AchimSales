"""Top-level pages."""

# === What's in this file ===
# For the foundation smoke deploy this is a single landing page that proves the
# app mounts, renders a real template, reads its database, and is themed in the
# live-blue look. It is intentionally public right now -- real Entra login and
# the reports list replace it in the auth and shell phases.
#
# index() -- the landing page: shows the app is alive and which slot it's on

from __future__ import annotations

from flask import Blueprint, render_template

from ..app import get_config, get_db
from ..auth.decorators import require_login
from ..auth.session import current_principal

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
@require_login
def index():
    config = get_config()
    db = get_db()

    schema_ready = False
    try:
        with db.precious() as conn:
            schema_ready = conn.fetchone(
                "SELECT 1 FROM app_meta WHERE key = 'booted_at'"
            ) is not None
    except Exception:  # noqa: BLE001 - the page still renders if setup hasn't finished
        schema_ready = False

    return render_template(
        "index.html",
        mount_path=config.mount_path,
        env=config.app_env,
        schema_ready=schema_ready,
        principal=current_principal(),
    )
