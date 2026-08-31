"""Supervisor: bootstrap first, then Gunicorn + worker share fate."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "supervise-web.sh"


def _chmod(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_supervise_bootstrap_failure_does_not_start_children(tmp_path: Path):
    env = {
        **os.environ,
        "STARTUP_ROOT": str(tmp_path),
        "GUNICORN_CMD": "echo gunicorn-started",
        "WORKER_CMD": "echo worker-started",
        "BOOTSTRAP_CMD": "false",
    }
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "bootstrap failed" in out
    assert "gunicorn-started" not in out
    assert "worker-started" not in out


def test_supervise_stops_peer_when_one_child_exits(tmp_path: Path):
    guni = tmp_path / "guni.sh"
    work = tmp_path / "work.sh"
    guni.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    work.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
    _chmod(guni)
    _chmod(work)
    env = {
        **os.environ,
        "STARTUP_ROOT": str(tmp_path),
        "GUNICORN_CMD": f"bash {guni}",
        "WORKER_CMD": f"bash {work}",
        "BOOTSTRAP_CMD": "true",
    }
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 7
    assert "a child exited" in out
