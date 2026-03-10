"""Entry point for Azure App Service (gunicorn)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webapp.app import app  # noqa: E402, F401
