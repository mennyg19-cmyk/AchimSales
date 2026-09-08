"""Build the allowlisted runtime artifact used by CI and emergency deploys."""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATHS = (
    "wsgi.py",
    "wsgi_dispatch.py",
    "app.py",
    "startup.sh",
    "supervise-web.sh",
    "gunicorn.conf.py",
    "litestream.yml",
    "webapp",
    "v3",
    "rebuild",
    "config",
    "core",
    "data",
    "reports",
)
EXCLUDED_PARTS = {
    ".env",
    ".git",
    ".scratch",
    ".cursor",
    ".codegraph",
    "logs",
    "app.zip",
    "tests",
    "tools",
    "runbooks",
    "go-live",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".data",
    ".rebuild-data",
}


def _include(path: Path) -> bool:
    return not any(part in EXCLUDED_PARTS or part.endswith(".md") for part in path.parts)


def artifact_files() -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    for relative_path in RUNTIME_PATHS:
        source = ROOT / relative_path
        if source.is_file():
            files.append((source, source.relative_to(ROOT)))
        elif source.is_dir():
            files.extend(
                (candidate, candidate.relative_to(ROOT))
                for candidate in source.rglob("*")
                if candidate.is_file() and _include(candidate.relative_to(ROOT))
            )
    files.append((ROOT / "webapp" / "requirements.txt", Path("requirements.txt")))
    return files


def build_directory(destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    for source, relative_path in artifact_files():
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def build_zip(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
        for source, relative_path in artifact_files():
            archive.write(source, relative_path.as_posix())


def main() -> None:
    parser = argparse.ArgumentParser()
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--dest", type=Path)
    output.add_argument("--zip", type=Path)
    arguments = parser.parse_args()
    if arguments.dest:
        build_directory(arguments.dest)
    else:
        build_zip(arguments.zip)


if __name__ == "__main__":
    main()
