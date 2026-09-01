"""Local entry: `python app.py` serves the same WSGI app as Azure gunicorn."""
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from wsgi import application  # noqa: E402, F401

if __name__ == "__main__":
    from werkzeug.serving import run_simple

    port = int(os.environ.get("PORT", "5001"))
    run_simple("0.0.0.0", port, application, use_reloader=False, use_debugger=True)
