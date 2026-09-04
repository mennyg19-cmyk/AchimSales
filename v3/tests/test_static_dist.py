"""Lock the deployed front-end output to the esbuild entrypoints and public files."""

from __future__ import annotations

from pathlib import Path


V3_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIST = V3_ROOT / "web" / "static_dist"
PUBLIC = V3_ROOT / "web" / "static_src" / "public"
EXPECTED_BUNDLES = {
    "css/main.css",
    "js/main.js",
    "js/report.js",
    "js/schedules.js",
    "js/settings.js",
    "js/admin.js",
    "js/dashboard.js",
    "js/db_explorer.js",
    "js/notif_diag.js",
}


def test_static_dist_matches_esbuild_outputs_and_public_files():
    public_files = {
        source.relative_to(PUBLIC).as_posix()
        for source in PUBLIC.rglob("*")
        if source.is_file()
    }
    expected = EXPECTED_BUNDLES | public_files
    actual = {
        source.relative_to(STATIC_DIST).as_posix()
        for source in STATIC_DIST.rglob("*")
        if source.is_file() and source.suffix != ".map"
    }

    assert actual == expected, "Run `cd v3 && npm run build` to refresh static_dist."
    for relative_path in EXPECTED_BUNDLES:
        assert (STATIC_DIST / relative_path).stat().st_size > 0
    for relative_path in public_files:
        assert (STATIC_DIST / relative_path).read_bytes() == (PUBLIC / relative_path).read_bytes()
