"""The Flask site has no D365 OData path. CLI/Automation keep theirs outside v3/."""

from __future__ import annotations

import ast
import re
from pathlib import Path

V3_ROOT = Path(__file__).resolve().parents[1]

# Frozen applied migration. Do not edit 0016; 0022 drops the table.
_SKIP_NAMES = {"0016_report_sources.sql"}
_SKIP_DIRS = {".venv", "node_modules", ".codegraph", ".pytest_cache", "vendor", "__pycache__"}
_SKIP_SUFFIXES = {".map", ".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".ico"}
_ODATA_WORD = re.compile(r"(?<![a-z])odata(?![a-z])", re.I)


def test_v3_tree_has_no_d365_odata_mentions():
    hits: list[str] = []
    for path in V3_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in _SKIP_SUFFIXES:
            continue
        if path.name in _SKIP_NAMES or path.name == Path(__file__).name:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        stripped = text.replace("@odata.type", "").replace("@odata.Type", "")
        if _ODATA_WORD.search(stripped):
            hits.append(str(path.relative_to(V3_ROOT)))
    assert hits == [], f"D365 leftovers under v3/: {hits}"


def test_v3_web_does_not_import_cli_report_runners():
    banned: list[str] = []
    for path in (V3_ROOT / "web").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mod = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "reports" or alias.name.startswith("reports."):
                        banned.append(f"{path.relative_to(V3_ROOT)}:{node.lineno} import {alias.name}")
                continue
            if mod == "reports" or mod.startswith("reports."):
                banned.append(f"{path.relative_to(V3_ROOT)}:{node.lineno} from {mod}")
    assert banned == []
