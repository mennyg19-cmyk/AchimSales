"""Empty-disk Litestream restore must refuse a prod boot (startup.sh)."""

from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "v3"


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


def _base_env(tmp_path: Path, root: Path, **over) -> dict:
    env = {
        **os.environ,
        "STARTUP_ROOT": str(root),
        "STARTUP_SKIP_PIP": "1",
        "APP_ENV": "prod",
        "PYTHONPATH": str(V3) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    env.update(over)
    return env


def _prod_litestream_env(tmp_path: Path, root: Path, fake_ls: Path, precious: Path) -> dict:
    return _base_env(
        tmp_path,
        root,
        LITESTREAM_BIN=str(fake_ls),
        LITESTREAM_AZURE_ACCOUNT_KEY="test-key",
        LITESTREAM_AZURE_ACCOUNT_NAME="acct",
        LITESTREAM_AZURE_CONTAINER="container",
        LITESTREAM_AZURE_SITE_PATH="site-precious.db",
        SITE_PRECIOUS_DB_PATH=str(precious),
        PATH=str(fake_ls.parent) + os.pathsep + os.environ.get("PATH", ""),
    )


def _stub_wwwroot(tmp_path: Path) -> Path:
    root = tmp_path / "wwwroot"
    root.mkdir()
    (root / "litestream.yml").write_text("dbs: []\n", encoding="utf-8")
    (root / "gunicorn.conf.py").write_text("# test stub\n", encoding="utf-8")
    return root


def _fake_litestream(bin_dir: Path, script: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_ls = bin_dir / "litestream"
    fake_ls.write_text(script, encoding="utf-8")
    fake_ls.chmod(fake_ls.stat().st_mode | stat.S_IEXEC)
    return fake_ls


def _users_sqlite(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    conn.execute("INSERT INTO users(email) VALUES ('ops@achimonline.com')")
    conn.commit()
    conn.close()


def test_prod_empty_disk_after_restore_refuses_boot(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    fake_ls = _fake_litestream(tmp_path / "bin", "#!/bin/sh\nexit 0\n")
    precious = tmp_path / "data" / "precious.db"
    proc = _run_startup(_prod_litestream_env(tmp_path, root, fake_ls, precious), tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "refusing prod boot with empty durable state" in out
    assert not precious.exists()
    marker = precious.with_name(".litestream-restore-failed")
    assert marker.is_file()


def test_prod_without_serving_path_refuses_boot(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    env = _base_env(
        tmp_path,
        root,
        LITESTREAM_BIN=str(tmp_path / "missing-litestream"),
        PRECIOUS_DB_PATH=str(tmp_path / "data" / "test.db"),
        LITESTREAM_AZURE_PATH="test-precious.db",
    )
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "SITE_PRECIOUS_DB_PATH or BETA_PRECIOUS_DB_PATH is required" in out


def test_prod_without_replica_path_refuses_boot(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    env = _base_env(
        tmp_path,
        root,
        LITESTREAM_BIN=str(tmp_path / "missing-litestream"),
        SITE_PRECIOUS_DB_PATH=str(tmp_path / "data" / "precious.db"),
        LITESTREAM_AZURE_ACCOUNT_KEY="test-key",
        LITESTREAM_AZURE_ACCOUNT_NAME="acct",
        LITESTREAM_AZURE_CONTAINER="container",
        LITESTREAM_AZURE_PATH="test-precious.db",
    )
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "SITE_PATH (or BETA_PATH alias) are required" in out


def test_prod_without_litestream_refuses_boot(tmp_path: Path):
    root = tmp_path / "wwwroot"
    root.mkdir()
    env = _base_env(
        tmp_path,
        root,
        LITESTREAM_BIN=str(tmp_path / "missing-litestream"),
        SITE_PRECIOUS_DB_PATH=str(tmp_path / "data" / "precious.db"),
        LITESTREAM_AZURE_ACCOUNT_KEY="test-key",
        LITESTREAM_AZURE_ACCOUNT_NAME="acct",
        LITESTREAM_AZURE_CONTAINER="container",
        LITESTREAM_AZURE_SITE_PATH="site-precious.db",
    )
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "Litestream is required" in out


def test_prod_mixed_case_app_env_still_requires_serving_path(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    env = _base_env(
        tmp_path,
        root,
        APP_ENV="Prod",
        LITESTREAM_BIN=str(tmp_path / "missing-litestream"),
        PRECIOUS_DB_PATH=str(tmp_path / "data" / "test.db"),
        LITESTREAM_AZURE_PATH="test-precious.db",
    )
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "SITE_PRECIOUS_DB_PATH or BETA_PRECIOUS_DB_PATH is required" in out
    assert "litestream not active; launching" not in out


def test_prod_padded_app_env_still_requires_litestream(tmp_path: Path):
    root = tmp_path / "wwwroot"
    root.mkdir()
    env = _base_env(
        tmp_path,
        root,
        APP_ENV=" prod ",
        LITESTREAM_BIN=str(tmp_path / "missing-litestream"),
        SITE_PRECIOUS_DB_PATH=str(tmp_path / "data" / "precious.db"),
        LITESTREAM_AZURE_ACCOUNT_KEY="test-key",
        LITESTREAM_AZURE_ACCOUNT_NAME="acct",
        LITESTREAM_AZURE_CONTAINER="container",
        LITESTREAM_AZURE_SITE_PATH="site-precious.db",
    )
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "Litestream is required" in out
    assert "litestream not active; launching" not in out


def test_unknown_app_env_refuses_boot(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    env = _base_env(
        tmp_path,
        root,
        APP_ENV="staging",
        SITE_PRECIOUS_DB_PATH=str(tmp_path / "data" / "precious.db"),
    )
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "APP_ENV must be 'dev' or 'prod'" in out


def test_dev_without_litestream_does_not_use_prod_gates(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    tools = root / "tools"
    tools.mkdir()
    supervise = tools / "supervise-web.sh"
    supervise.write_text("#!/bin/sh\necho supervise-ok\nexit 0\n", encoding="utf-8")
    supervise.chmod(supervise.stat().st_mode | 0o111)
    env = _base_env(tmp_path, root, APP_ENV="DEV")
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0
    assert "supervise-ok" in out
    assert "SITE_PRECIOUS_DB_PATH or BETA_PRECIOUS_DB_PATH is required" not in out
    assert "Litestream is required" not in out


def test_prod_home_path_refuses_boot(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    env = _base_env(
        tmp_path,
        root,
        LITESTREAM_BIN=str(tmp_path / "missing-litestream"),
        SITE_PRECIOUS_DB_PATH="/home/site/v3data/precious.db",
        LITESTREAM_AZURE_ACCOUNT_KEY="test-key",
        LITESTREAM_AZURE_ACCOUNT_NAME="acct",
        LITESTREAM_AZURE_CONTAINER="container",
        LITESTREAM_AZURE_SITE_PATH="site-precious.db",
    )
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "serving db on /home" in out


def test_prod_home_via_dotdot_refuses_boot(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    env = _base_env(
        tmp_path,
        root,
        LITESTREAM_BIN=str(tmp_path / "missing-litestream"),
        SITE_PRECIOUS_DB_PATH="/tmp/../home/site/v3data/precious.db",
        LITESTREAM_AZURE_ACCOUNT_KEY="test-key",
        LITESTREAM_AZURE_ACCOUNT_NAME="acct",
        LITESTREAM_AZURE_CONTAINER="container",
        LITESTREAM_AZURE_SITE_PATH="site-precious.db",
    )
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "serving db on /home" in out


def test_prod_relative_serving_path_refuses_boot(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    env = _base_env(
        tmp_path,
        root,
        LITESTREAM_BIN=str(tmp_path / "missing-litestream"),
        SITE_PRECIOUS_DB_PATH="./precious.db",
        LITESTREAM_AZURE_ACCOUNT_KEY="test-key",
        LITESTREAM_AZURE_ACCOUNT_NAME="acct",
        LITESTREAM_AZURE_CONTAINER="container",
        LITESTREAM_AZURE_SITE_PATH="site-precious.db",
    )
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "must be absolute" in out


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
    env = _base_env(
        tmp_path,
        root,
        LITESTREAM_BIN=str(tmp_path / "missing-litestream"),
        LITESTREAM_AZURE_ACCOUNT_KEY="test-key",
        LITESTREAM_AZURE_ACCOUNT_NAME="acct",
        LITESTREAM_AZURE_CONTAINER="container",
        LITESTREAM_AZURE_SITE_PATH="site-precious.db",
        LITESTREAM_SHA256="0" * 64,
        SITE_PRECIOUS_DB_PATH=str(tmp_path / "data" / "precious.db"),
        PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
    )
    proc = _run_startup(env, tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "litestream checksum mismatch" in out
    assert "Litestream is required" in out
    assert not (tmp_path / "missing-litestream").exists()


def test_prod_zero_byte_db_refuses_boot(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    log = tmp_path / "ls.log"
    precious = tmp_path / "data" / "precious.db"
    fake_ls = _fake_litestream(
        tmp_path / "bin",
        "#!/bin/bash\n"
        f"echo \"$*\" >> '{log}'\n"
        "if [ \"$1\" = \"restore\" ]; then\n"
        "  dest=\"${@: -1}\"\n"
        "  mkdir -p \"$(dirname \"$dest\")\"\n"
        "  : > \"$dest\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
    )
    proc = _run_startup(_prod_litestream_env(tmp_path, root, fake_ls, precious), tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "missing or empty after restore" in out
    assert "refusing prod boot with empty durable state" in out
    assert precious.with_name(".litestream-restore-failed").is_file()


def test_prod_corrupt_db_refuses_boot(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    log = tmp_path / "ls.log"
    precious = tmp_path / "data" / "precious.db"
    fake_ls = _fake_litestream(
        tmp_path / "bin",
        "#!/bin/bash\n"
        f"echo \"$*\" >> '{log}'\n"
        "if [ \"$1\" = \"restore\" ]; then\n"
        "  dest=\"${@: -1}\"\n"
        "  mkdir -p \"$(dirname \"$dest\")\"\n"
        "  printf 'not-a-sqlite\\n' > \"$dest\"\n"
        "  exit 0\n"
        "fi\n"
        "exit 0\n",
    )
    proc = _run_startup(_prod_litestream_env(tmp_path, root, fake_ls, precious), tmp_path)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "failed integrity check" in out
    assert precious.with_name(".litestream-restore-failed").is_file()


def test_prod_beta_alias_restores_only_serving_db(tmp_path: Path):
    root = _stub_wwwroot(tmp_path)
    log = tmp_path / "ls.log"
    serving = tmp_path / "betadata" / "precious.db"
    leftover_test = tmp_path / "v3data" / "precious.db"
    golden = tmp_path / "golden.db"
    _users_sqlite(golden)
    fake_ls = _fake_litestream(
        tmp_path / "bin",
        "#!/bin/bash\n"
        f"echo \"$*\" >> '{log}'\n"
        "if [ \"$1\" = \"restore\" ]; then\n"
        "  dest=\"${@: -1}\"\n"
        "  mkdir -p \"$(dirname \"$dest\")\"\n"
        f"  cp '{golden}' \"$dest\"\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"replicate\" ]; then\n"
        "  exit 99\n"
        "fi\n"
        "exit 0\n",
    )
    env = _base_env(
        tmp_path,
        root,
        LITESTREAM_BIN=str(fake_ls),
        LITESTREAM_AZURE_ACCOUNT_KEY="test-key",
        LITESTREAM_AZURE_ACCOUNT_NAME="acct",
        LITESTREAM_AZURE_CONTAINER="container",
        LITESTREAM_AZURE_BETA_PATH="beta-precious.db",
        LITESTREAM_AZURE_PATH="test-precious.db",
        BETA_PRECIOUS_DB_PATH=str(serving),
        PRECIOUS_DB_PATH=str(leftover_test),
        PATH=str(fake_ls.parent) + os.pathsep + os.environ.get("PATH", ""),
    )
    proc = _run_startup(env, tmp_path)
    logged = log.read_text(encoding="utf-8") if log.is_file() else ""
    assert proc.returncode == 99
    assert logged.count("restore ") == 1
    assert str(serving) in logged
    assert str(leftover_test) not in logged
    assert serving.is_file()
    assert not leftover_test.exists()
