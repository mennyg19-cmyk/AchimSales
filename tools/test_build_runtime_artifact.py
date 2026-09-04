from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _artifact_members(destination: Path) -> set[str]:
    subprocess.run(
        [sys.executable, "tools/build_runtime_artifact.py", "--zip", str(destination)],
        cwd=ROOT,
        check=True,
    )
    with zipfile.ZipFile(destination) as archive:
        return set(archive.namelist())


def test_runtime_artifact_is_allowlisted(tmp_path):
    members = _artifact_members(tmp_path / "runtime.zip")
    directory = tmp_path / "runtime-dir"
    subprocess.run(
        [sys.executable, "tools/build_runtime_artifact.py", "--dest", str(directory)],
        cwd=ROOT,
        check=True,
    )

    assert {
        "wsgi.py",
        "startup.sh",
        "v3/web/static_dist/css/main.css",
        "webapp/app.py",
        "requirements.txt",
    } <= members
    assert "--hash=" in zipfile.ZipFile(tmp_path / "runtime.zip").read("requirements.txt").decode()
    assert not any(
        part in {".git", ".scratch", "node_modules", ".env"}
        for member in members
        for part in Path(member).parts
    )
    assert (directory / "v3/web/static_dist/css/main.css").is_file()
    assert "--hash=" in (directory / "requirements.txt").read_text(encoding="utf-8")


def test_runtime_lock_has_hashes_for_every_requirement():
    lock = (ROOT / "webapp/requirements.txt").read_text(encoding="utf-8")
    requirements = re.findall(r"(?m)^[a-zA-Z0-9_.-]+(?:\[[^]]+\])?==.+?(?=^[a-zA-Z0-9_.-]+(?:\[|==)|\Z)", lock, re.S)

    assert requirements
    assert all("--hash=" in requirement for requirement in requirements)
