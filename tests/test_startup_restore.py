"""Empty-disk Litestream restore must refuse a prod boot (startup.sh)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_startup(env: dict, cwd: Path) -> subprocess.CompletedProcess:
    script = ROOT / "startup.sh"
    return subprocess.run(
        ["bash", str(script)],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_prod_empty_disk_after_restore_refuses_boot(tmp_path: Path):
    root = tmp_path / "wwwroot"
    root.mkdir()
    (root / "litestream.yml").write_text("dbs: []\n", encoding="utf-8")
    (root / "gunicorn.conf.py").write_text("# test stub\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_ls = bin_dir / "litestream"
    fake_ls.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_ls.chmod(fake_ls.stat().st_mode | stat.S_IEXEC)

    precious = tmp_path / "data" / "precious.db"
    env = {
        **os.environ,
        "STARTUP_ROOT": str(root),
        "STARTUP_SKIP_PIP": "1",
        "LITESTREAM_BIN": str(fake_ls),
        "LITESTREAM_AZURE_ACCOUNT_KEY": "test-key",
        "PRECIOUS_DB_PATH": str(precious),
        "APP_ENV": "prod",
        "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
    }
    result = _run_startup(env, tmp_path)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "refusing prod boot with empty durable state" in out
    assert not precious.exists()
    marker = precious.with_name(".litestream-restore-failed")
    assert marker.is_file()


def test_prod_without_litestream_refuses_boot(tmp_path: Path):
    root = tmp_path / "wwwroot"
    root.mkdir()
    env = {
        **os.environ,
        "STARTUP_ROOT": str(root),
        "STARTUP_SKIP_PIP": "1",
        "LITESTREAM_BIN": str(tmp_path / "missing-litestream"),
        "APP_ENV": "prod",
        "PRECIOUS_DB_PATH": str(tmp_path / "data" / "precious.db"),
    }
    result = _run_startup(env, tmp_path)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "Litestream is required" in out


def test_prod_bad_litestream_checksum_refuses_boot(tmp_path: Path):
    root = tmp_path / "wwwroot"
    root.mkdir()
    (root / "litestream.yml").write_text("dbs: []\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_curl = bin_dir / "curl"
    fake_curl.write_text(
        "#!/bin/sh\n"
        "out=\"\"\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = \"-o\" ]; then out=\"$2\"; shift 2; continue; fi\n"
        "  shift\n"
        "done\n"
        "if [ -n \"$out\" ]; then printf 'not-a-tarball\\n' > \"$out\"; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IEXEC)
    env = {
        **os.environ,
        "STARTUP_ROOT": str(root),
        "STARTUP_SKIP_PIP": "1",
        "LITESTREAM_BIN": str(tmp_path / "missing-litestream"),
        "LITESTREAM_AZURE_ACCOUNT_KEY": "test-key",
        "LITESTREAM_SHA256": "0" * 64,
        "PRECIOUS_DB_PATH": str(tmp_path / "data" / "precious.db"),
        "APP_ENV": "prod",
        "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
    }
    result = _run_startup(env, tmp_path)
    out = result.stdout + result.stderr
    assert result.returncode == 1
    assert "litestream checksum mismatch" in out
    assert "Litestream is required" in out
    assert not (tmp_path / "missing-litestream").exists()
