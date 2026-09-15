"""Prove the Azure process model: gunicorn + UvicornWorker + /healthz."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_startup_script_is_azure_shaped():
    text = (ROOT / "startup.sh").read_text(encoding="utf-8")
    assert "uvicorn.workers.UvicornWorker" in text
    assert "0.0.0.0" in text
    assert "${PORT" in text
    assert "main:app" in text
    assert "achim-sales-reports" in text  # warning to never point live at this
    assert "GUNICORN_TIMEOUT:-180" in text


def test_gunicorn_worker_serves_healthz():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "gunicorn",
            "--worker-class", "uvicorn.workers.UvicornWorker",
            "--bind", f"127.0.0.1:{port}",
            "--workers", "1",
            "--timeout", "15",
            "main:app",
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    url = f"http://127.0.0.1:{port}/healthz"
    try:
        last_err = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(url, timeout=1) as resp:
                    assert resp.status == 200
                    assert b'"ok"' in resp.read()
                return
            except (urllib.error.URLError, ConnectionError, TimeoutError) as err:
                last_err = err
                if proc.poll() is not None:
                    err_out = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
                    raise AssertionError(f"gunicorn exited {proc.returncode}: {err_out}") from err
                time.sleep(0.15)
        raise AssertionError(f"gunicorn never answered /healthz: {last_err}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
