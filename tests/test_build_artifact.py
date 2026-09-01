"""The deploy zip includes the supervisor script the App Service actually runs."""

import subprocess
from pathlib import Path

import pytest

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


def test_untracked_env_and_db_are_omitted(tmp_path):
    (tmp_path / "app.py").write_text("x\n")
    v3 = tmp_path / "v3"
    v3.mkdir()
    (v3 / "keep.txt").write_text("ok\n")
    (v3 / ".env").write_text("SECRET=1\n")
    data = v3 / ".data"
    data.mkdir()
    (data / "precious.db").write_bytes(b"sqlite")
    allow = tmp_path / "allow.txt"
    allow.write_text("app.py\nv3/\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "app.py", "v3/keep.txt"], cwd=tmp_path, check=True)
    names = {p.as_posix() for p in iter_artifact_files(tmp_path, allowlist_path=allow)}
    assert names == {"app.py", "v3/keep.txt"}


def test_missing_git_refuses_to_pack(tmp_path):
    (tmp_path / "app.py").write_text("x\n")
    allow = tmp_path / "allow.txt"
    allow.write_text("app.py\n")
    with pytest.raises(RuntimeError, match="git checkout"):
        iter_artifact_files(tmp_path, allowlist_path=allow)


def test_deploy_ps1_matches_ci_gates():
    text = (ROOT / "deploy.ps1").read_text()
    assert "npm is required" in text
    assert "pytest v3/tests tests" not in text
    assert "v3 pytest failed" in text
    assert "root pytest failed" in text
