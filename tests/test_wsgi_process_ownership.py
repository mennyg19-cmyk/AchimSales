"""Process-boundary checks for the App Service entry points."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_wsgi_does_not_bootstrap_v3_or_beta_during_import():
    source = (ROOT / "wsgi.py").read_text(encoding="utf-8")
    assert "v3-bootstrap" not in source
    assert "beta-bootstrap" not in source
    assert "bootstrap_background" not in source


def test_supervisor_launches_http_and_worker_siblings():
    source = (ROOT / "supervise-web.sh").read_text(encoding="utf-8")
    assert "wsgi:application" in source
    assert "python3 -m web.jobs.worker_main" in source
    assert "wait -n" in source
    assert "trap shutdown SIGTERM SIGINT" in source
