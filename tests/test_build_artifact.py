"""The deploy zip includes the supervisor script the App Service actually runs."""

from pathlib import Path

from tools.build_artifact import iter_artifact_files, write_zip

ROOT = Path(__file__).resolve().parents[1]


def test_artifact_includes_supervisor_and_wsgi():
    names = {p.as_posix() for p in iter_artifact_files(ROOT)}
    assert "tools/supervise-web.sh" in names
    assert "wsgi.py" in names
    assert "startup.sh" in names
    assert "requirements.txt" in names
    assert not any(p.startswith("v3/web/static_src/") for p in names)
    assert not any(p.startswith("v3/tests/") for p in names)
    assert not any(p.endswith(".map") for p in names)
    assert not any("/node_modules/" in p for p in names)


def test_zip_round_trip(tmp_path):
    zip_path = tmp_path / "app.zip"
    files = write_zip(zip_path, root=ROOT)
    assert zip_path.stat().st_size > 0
    assert any(p.as_posix() == "tools/supervise-web.sh" for p in files)
