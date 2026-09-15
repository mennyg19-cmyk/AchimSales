"""Silent dual-path workbook parity + daily digest."""

from __future__ import annotations

from pathlib import Path

from web.config import Config
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.app_settings import AppSettingsRepository
from web.data.repositories.outbox import OutboxRepository
from web.delivery.email import EmailService
from web.delivery.parity_digest import send_parity_digest
from web.delivery.service import DeliveryService
from web.delivery.sharepoint import SharePointService
from web.delivery.workbook_parity import (
    ViewWorkbookParityRepository,
    format_digest,
    parity_root,
    run_parity_files,
)
from web.reporting.cache import ReportCache
from web.reporting.runner import ReportRunner


def _db(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    return db


def _cfg(tmp_path) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", new_app_marker=True, outbox_dir=tmp_path / "outbox",
    )


def _payload():
    return {
        "tabs": [{
            "key": "summary", "name": "Summary",
            "columns": [
                {"field": "a", "header": "A"},
                {"field": "b", "header": "B"},
            ],
            "rows": [{"a": "x", "b": 1}, {"a": "y", "b": 2}],
        }],
    }


def _layout_hide_b():
    return {
        "order": ["summary"],
        "views": {"summary": {"group": [], "hidden": ["b"]}},
    }


def _layout_show_all():
    return {
        "order": ["summary"],
        "views": {"summary": {"group": []}},
    }


def test_migration_creates_parity_table(tmp_path):
    db = _db(tmp_path)
    with db.precious() as conn:
        cols = {
            r["name"]
            for r in conn.execute("PRAGMA table_info(view_workbook_parity)")
        }
    assert "matched" in cols and "digest_date" in cols


def test_parity_match_writes_pair_and_scores(tmp_path):
    root = tmp_path / "view-parity"
    layout = _layout_show_all()
    result = run_parity_files(
        root=root, report_key="ordered", view_name="Daily",
        schedule_name="Daily run", payload=_payload(),
        new_layout=layout, old_layout=layout,
    )
    assert result.matched
    assert Path(result.old_path).is_file()
    assert Path(result.new_path).is_file()
    assert result.old_path.endswith("__old.xlsx")
    assert result.new_path.endswith("__new.xlsx")


def test_parity_mismatch_records_diff_summary(tmp_path):
    db = _db(tmp_path)
    root = tmp_path / "view-parity"
    result = run_parity_files(
        root=root, report_key="ordered", view_name="Daily",
        schedule_name="Daily run", payload=_payload(),
        new_layout=_layout_hide_b(), old_layout=_layout_show_all(),
    )
    assert not result.matched
    assert "Summary" in result.diff_summary or "row 0" in result.diff_summary
    rid = ViewWorkbookParityRepository(db).record(
        report_key="ordered", view_name="Daily", schedule_name="Daily run",
        result=result,
    )
    assert rid > 0
    with db.precious() as conn:
        row = conn.execute(
            "SELECT matched, diff_summary FROM view_workbook_parity WHERE id=?",
            (rid,),
        ).fetchone()
    assert row["matched"] == 0
    assert row["diff_summary"]


def test_delivery_parity_failure_does_not_block_send(tmp_path, monkeypatch):
    db = _db(tmp_path)
    cfg = _cfg(tmp_path)
    email = EmailService(cfg, OutboxRepository(db), SharePointService(cfg))
    payload = _payload()
    svc = DeliveryService(
        ReportRunner(ReportCache(db)),
        lambda key: (lambda params, vk: payload),
        email,
        db=db,
        precious_db_path=cfg.precious_db_path,
    )

    def boom(*_a, **_k):
        raise RuntimeError("parity explode")

    monkeypatch.setattr("web.delivery.service.run_parity_files", boom)
    outcome = svc.run_and_deliver(
        report_key="ordered", identity="u@x.com", visible_salesman_keys=None,
        builder_version=1, params={}, layout=_layout_show_all(),
        recipients="a@x.com", subject="S", report_name="Ordered",
        compare_layout=_layout_hide_b(),
        parity_view_name="Daily",
    )
    assert outcome.result.ok
    assert outcome.row_count == 2


def test_delivery_skips_parity_on_huge_grid(tmp_path, monkeypatch):
    db = _db(tmp_path)
    cfg = _cfg(tmp_path)
    email = EmailService(cfg, OutboxRepository(db), SharePointService(cfg))
    from web.delivery import service as delivery_service

    huge = {
        "tabs": [{
            "key": "summary", "name": "Summary",
            "columns": [{"field": "a", "header": "A"}],
            "rows": [{"a": i} for i in range(delivery_service._MAX_PARITY_GRID_ROWS + 1)],
        }],
    }
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("parity must not run for huge grids")

    monkeypatch.setattr("web.delivery.service.run_parity_files", boom)
    svc = DeliveryService(
        ReportRunner(ReportCache(db)),
        lambda key: (lambda params, vk: huge),
        email,
        db=db,
        precious_db_path=cfg.precious_db_path,
    )
    outcome = svc.run_and_deliver(
        report_key="ordered", identity="u@x.com", visible_salesman_keys=None,
        builder_version=1, params={}, layout=_layout_show_all(),
        recipients="a@x.com", subject="S", report_name="Ordered",
        compare_layout=_layout_show_all(),
        parity_view_name="Ordered",
    )
    assert outcome.result.ok
    assert called["n"] == 0
    with db.precious() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM view_workbook_parity").fetchone()["n"] == 0


def test_delivery_records_match_when_layouts_agree(tmp_path):
    db = _db(tmp_path)
    cfg = _cfg(tmp_path)
    email = EmailService(cfg, OutboxRepository(db), SharePointService(cfg))
    payload = _payload()
    layout = _layout_show_all()
    svc = DeliveryService(
        ReportRunner(ReportCache(db)),
        lambda key: (lambda params, vk: payload),
        email,
        db=db,
        precious_db_path=cfg.precious_db_path,
    )
    outcome = svc.run_and_deliver(
        report_key="ordered", identity="u@x.com", visible_salesman_keys=None,
        builder_version=1, params={}, layout=layout,
        recipients="a@x.com", subject="S", report_name="Ordered",
        compare_layout=layout,
        parity_view_name="Daily",
        parity_schedule_kind="personal",
        parity_schedule_id=9,
    )
    assert outcome.result.ok
    with db.precious() as conn:
        rows = conn.execute("SELECT * FROM view_workbook_parity").fetchall()
    assert len(rows) == 1
    assert rows[0]["matched"] == 1
    assert rows[0]["view_name"] == "Daily"
    assert Path(rows[0]["old_path"]).is_file()
    assert Path(rows[0]["new_path"]).is_file()
    assert parity_root(cfg.precious_db_path) == cfg.precious_db_path.parent / "view-parity"


def test_digest_sends_once_per_day(tmp_path):
    db = _db(tmp_path)
    cfg = _cfg(tmp_path)
    settings = AppSettingsRepository(db)
    settings.set_view_parity_digest_emails(["menny@x.com"])
    repo = ViewWorkbookParityRepository(db)
    layout = _layout_show_all()
    result = run_parity_files(
        root=tmp_path / "view-parity", report_key="ordered", view_name="V",
        schedule_name="S", payload=_payload(),
        new_layout=layout, old_layout=layout,
    )
    # Stamp created_at inside yesterday Eastern window via direct insert override.
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    eastern = ZoneInfo("America/New_York")
    yesterday = (datetime.now(eastern).date() - timedelta(days=1)).isoformat()
    start_utc = datetime.fromisoformat(f"{yesterday}T12:00:00").replace(
        tzinfo=eastern,
    ).astimezone(timezone.utc).isoformat()
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO view_workbook_parity("
            " created_at, report_key, view_name, view_id, schedule_kind,"
            " schedule_id, schedule_name, matched, row_count, old_path,"
            " new_path, diff_summary)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                start_utc, "ordered", "V", None, "personal", 1, "S",
                1 if result.matched else 0, result.row_count,
                result.old_path, result.new_path, result.diff_summary,
            ),
        )

    class FakeEmail:
        def __init__(self):
            self.calls = []

        def deliver(self, **kwargs):
            self.calls.append(kwargs)

            class R:
                ok = True
                error = ""

            return R()

    email = FakeEmail()
    status = send_parity_digest(db=db, email_service=email, day=yesterday)
    assert status.startswith("sent")
    assert len(email.calls) == 1
    assert "menny@x.com" in email.calls[0]["recipients_raw"]
    assert "match" in email.calls[0]["subject"].lower() or "MATCH" in email.calls[0]["body_text"]

    status2 = send_parity_digest(db=db, email_service=email, day=yesterday)
    assert status2.startswith("already sent")
    assert len(email.calls) == 1


def test_format_digest_lists_diffs():
    subject, body = format_digest("2026-09-14", [
        {
            "matched": 1, "report_key": "ordered", "view_name": "Daily",
            "schedule_name": "AM", "row_count": 10,
            "old_path": "/o.xlsx", "new_path": "/n.xlsx", "diff_summary": "",
        },
        {
            "matched": 0, "report_key": "ordered", "view_name": "Open",
            "schedule_name": "PM", "row_count": 3,
            "old_path": "/o2.xlsx", "new_path": "/n2.xlsx",
            "diff_summary": "summary: row mismatch",
        },
    ])
    assert "1 match, 1 diff" in subject
    assert "DIFF" in body and "MATCH" in body
    assert "summary: row mismatch" in body


def test_parity_filenames_unique_same_second(tmp_path):
    root = tmp_path / "view-parity"
    layout = _layout_show_all()
    a = run_parity_files(
        root=root, report_key="ordered", view_name="Daily",
        schedule_name="full", payload=_payload(),
        new_layout=layout, old_layout=layout,
    )
    b = run_parity_files(
        root=root, report_key="ordered", view_name="Daily",
        schedule_name="split-A", payload=_payload(),
        new_layout=layout, old_layout=layout,
    )
    assert a.new_path != b.new_path
    assert a.old_path != b.old_path
    assert Path(a.new_path).is_file() and Path(b.new_path).is_file()


def test_parity_always_builds_old_workbook(tmp_path):
    """Delivered new bytes must still be compared to a real old-layout build."""
    root = tmp_path / "view-parity"
    payload = _payload()
    new_layout = _layout_hide_b()
    old_layout = _layout_show_all()
    from web.delivery.layout import apply_layout, expand_clones
    from web.reporting.export import build_workbook

    delivered = build_workbook(
        apply_layout(expand_clones(payload, new_layout), new_layout), new_layout,
    )
    # Same canonical shape after dual-write would previously short-circuit to MATCH.
    from web.data.normalized_views import canonicalize_layout
    assert canonicalize_layout(new_layout) != canonicalize_layout(old_layout)
    result = run_parity_files(
        root=root, report_key="ordered", view_name="Daily",
        schedule_name="S", payload=payload,
        new_layout=new_layout, old_layout=old_layout,
        delivered_xlsx=delivered,
    )
    assert not result.matched
    assert Path(result.old_path).read_bytes() != Path(result.new_path).read_bytes()


def test_digest_retries_undigested_after_failed_day(tmp_path):
    db = _db(tmp_path)
    settings = AppSettingsRepository(db)
    settings.set_view_parity_digest_emails(["menny@x.com"])
    layout = _layout_show_all()
    result = run_parity_files(
        root=tmp_path / "view-parity", report_key="ordered", view_name="V",
        schedule_name="S", payload=_payload(),
        new_layout=layout, old_layout=layout,
    )
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo

    eastern = ZoneInfo("America/New_York")
    two_days_ago = (datetime.now(eastern).date() - timedelta(days=2)).isoformat()
    yesterday = (datetime.now(eastern).date() - timedelta(days=1)).isoformat()
    ts = datetime.fromisoformat(f"{two_days_ago}T12:00:00").replace(
        tzinfo=eastern,
    ).astimezone(timezone.utc).isoformat()
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO view_workbook_parity("
            " created_at, report_key, view_name, view_id, schedule_kind,"
            " schedule_id, schedule_name, matched, row_count, old_path,"
            " new_path, diff_summary)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ts, "ordered", "V", "co-x", "personal", 1, "S",
                1, result.row_count, result.old_path, result.new_path, "",
            ),
        )
    settings.set_view_parity_digest_sent_day(yesterday)

    class FakeEmail:
        def __init__(self):
            self.calls = []

        def deliver(self, **kwargs):
            self.calls.append(kwargs)

            class R:
                ok = True
                error = ""

            return R()

    email = FakeEmail()
    status = send_parity_digest(db=db, email_service=email, day=yesterday)
    assert status.startswith("sent")
    assert len(email.calls) == 1
    with db.precious() as conn:
        left = conn.execute(
            "SELECT COUNT(*) AS n FROM view_workbook_parity WHERE digest_date IS NULL"
        ).fetchone()["n"]
    assert left == 0
