"""Entry point for Azure App Service (gunicorn) and local development."""
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from webapp.app import app  # noqa: E402, F401

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
