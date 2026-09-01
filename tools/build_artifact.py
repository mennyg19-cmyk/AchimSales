"""Copy the Production allowlist into a directory or zip.

CI and deploy.ps1 must use this file. Do not invent a second exclude list.
Packs git-tracked files only so a dirty checkout cannot ship .env or local DBs.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = Path(__file__).resolve().parent / "artifact-allowlist.txt"

SKIP_DIR_NAMES = {
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "static_src",
    "tests",
}
SKIP_SUFFIXES = {".map", ".pyc"}


def _includes(allowlist_path: Path | None = None) -> list[str]:
    path = allowlist_path or ALLOWLIST
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line.rstrip("/"))
    return lines


def _git_tracked(root: Path) -> set[str]:
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip() or f"exit {proc.returncode}"
        raise RuntimeError(f"artifact builder needs a git checkout (git ls-files failed: {err})")
    return {p.replace("\\", "/") for p in proc.stdout.decode("utf-8").split("\0") if p}


def _should_skip(rel: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in rel.parts):
        return True
    if rel.suffix in SKIP_SUFFIXES:
        return True
    return False


def iter_artifact_files(
    root: Path | None = None,
    *,
    allowlist_path: Path | None = None,
) -> list[Path]:
    """Repo-relative git-tracked paths that belong in the deploy artifact."""
    root = root or ROOT
    tracked = _git_tracked(root)
    out: list[Path] = []
    seen: set[Path] = set()
    for item in _includes(allowlist_path):
        path = root / item
        if not path.exists():
            raise FileNotFoundError(f"allowlist path missing: {item}")
        if path.is_file():
            rel = Path(item)
            if rel.as_posix() not in tracked:
                continue
            if rel not in seen:
                out.append(rel)
                seen.add(rel)
            continue
        for found in path.rglob("*"):
            if not found.is_file():
                continue
            rel = found.relative_to(root)
            if _should_skip(rel) or rel in seen:
                continue
            if rel.as_posix() not in tracked:
                continue
            out.append(rel)
            seen.add(rel)
    return sorted(out, key=lambda p: p.as_posix())


def stage(dest: Path, *, root: Path | None = None) -> list[Path]:
    root = root or ROOT
    dest.mkdir(parents=True, exist_ok=True)
    files = iter_artifact_files(root)
    for rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
    return files


def write_zip(zip_path: Path, *, root: Path | None = None) -> list[Path]:
    root = root or ROOT
    files = iter_artifact_files(root)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    # Some checkout mtimes are before 1980; zipfile rejects those.
    min_ts = 315532800
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            src = root / rel
            stamp = time.localtime(max(src.stat().st_mtime, min_ts))[:6]
            info = zipfile.ZipInfo(rel.as_posix(), date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, src.read_bytes())
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Production allowlist artifact")
    parser.add_argument("--out", type=Path, help="Stage files into this directory")
    parser.add_argument("--zip", dest="zip_path", type=Path, help="Write app.zip here")
    args = parser.parse_args(argv)
    if args.out is None and args.zip_path is None:
        parser.error("pass --out DIR and/or --zip FILE")
    if args.out is not None:
        files = stage(args.out)
        print(f"staged {len(files)} files into {args.out}")
    if args.zip_path is not None:
        files = write_zip(args.zip_path)
        print(f"wrote {len(files)} files to {args.zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
