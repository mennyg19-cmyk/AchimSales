"""Phase 5 delivery recovery: honest states, slot id, Graph unknown."""

from __future__ import annotations

import io
import urllib.error
from datetime import datetime, timezone

import pytest

from web.config import Config
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.delivery_legs import (
    DeliveryLegRepository, attempt_key, parse_scheduled_slot_id, scheduled_slot_id,
)
from web.data.repositories.jobs import JobRepository
from web.data.repositories.outbox import OutboxRepository
from web.data.repositories.schedules import PERSONAL, ScheduleRepository, ScheduleRunRepository
from web.data.repositories.users import UserRepository
from web.delivery.email import EmailService
from web.delivery.graph_mail import GraphMailError, GraphMailer, GraphUnknownError
from web.delivery.sharepoint import SharePointService
from web.delivery.states import FAILED, PREPARED, SENT, UNKNOWN
from web.scheduling.jobs import enqueue_leg_retry, enqueue_schedule_run


def _db(tmp_path) -> Database:
    d = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(d)
    return d


def _cfg(tmp_path, **over) -> Config:
    base = dict(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", outbox_dir=tmp_path / "outbox",
    )
    base.update(over)
    return Config(**base)


def test_pending_migrates_to_unknown(tmp_path):
    from pathlib import Path

    from web.data.migrate import apply_migrations

    precious = tmp_path / "p.db"
    root = Path(__file__).resolve().parents[1] / "web" / "data" / "migrations" / "precious"
    staging = tmp_path / "pre0023"
    staging.mkdir()
    for sql in root.glob("*.sql"):
        if sql.name[:4] >= "0023":
            continue
        (staging / sql.name).write_text(sql.read_text(encoding="utf-8"), encoding="utf-8")
    apply_migrations(precious, staging)
    import sqlite3
    conn = sqlite3.connect(precious)
    conn.execute(
        "INSERT INTO delivery_legs(run_id, attempt_key, kind, target, status)"
        " VALUES (1, 'legacy-pending', 'email', 'a@x.com', 'pending')"
    )
    conn.commit()
    conn.close()
    applied = apply_migrations(precious, root)
    assert any(name.startswith("0023_") for name in applied)
    assert any(name.startswith("0024_") for name in applied)
    assert any(name.startswith("0025_") for name in applied)
    db = Database(precious, tmp_path / "c.db")
    legs = DeliveryLegRepository(db)
    assert legs.get("legacy-pending").status == UNKNOWN
    assert legs.get("legacy-pending").status != "pending"


def test_crash_before_external_call_is_retryable(tmp_path):
    db = _db(tmp_path)
    jobs = JobRepository(db)
    jid = jobs.enqueue("schedule.run")
    jobs.claim_next()
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com", job_id=jid, slot_id="s1")
    jobs.recover_orphans()
    assert jobs.get(jid).status == "cancelled"
    assert legs.get(key).status == FAILED
    assert "before send" in legs.get(key).error
    assert legs.reopen_for_retry(key) is True
    assert legs.get(key).status == PREPARED


def test_crash_while_sending_email_is_unknown_not_retried(tmp_path):
    db = _db(tmp_path)
    jobs = JobRepository(db)
    jid = jobs.enqueue("schedule.run")
    jobs.claim_next()
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com", job_id=jid, slot_id="s1")
    legs.mark_sending(key)
    jobs.recover_orphans()
    assert jobs.get(jid).status == "cancelled"
    assert legs.get(key).status == UNKNOWN
    assert legs.is_settled(key)
    jobs.mark_success(jid, "late")
    assert jobs.get(jid).status == "cancelled"
    assert legs.prepare(key, run_id=1, kind="email", target="a@x.com") == "skip"


def test_crash_after_graph_accepted_commits_sent(tmp_path):
    db = _db(tmp_path)
    jobs = JobRepository(db)
    jid = jobs.enqueue("report.deliver")
    jobs.claim_next()
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="m1", kind="email", target="a@x.com")
    legs.prepare(key, run_id=None, kind="email", target="a@x.com", job_id=jid, slot_id="m1")
    legs.mark_sending(key)
    legs.mark_accepted(key, remote_id="graph-ok")
    jobs.recover_orphans()
    assert legs.get(key).status == SENT


def test_slot_id_does_not_use_execution_day():
    monday = scheduled_slot_id(
        schedule_type="master", schedule_id=9, slot_day="2026-08-31")
    tuesday = scheduled_slot_id(
        schedule_type="master", schedule_id=9, slot_day="2026-09-01")
    k_mon = attempt_key(slot_id=monday, kind="email", target="a@x.com")
    k_tue = attempt_key(slot_id=tuesday, kind="email", target="a@x.com")
    assert k_mon != k_tue
    assert k_mon == attempt_key(slot_id=monday, kind="email", target="a@x.com")


def test_enqueue_freezes_slot_day(tmp_path):
    db = _db(tmp_path)
    now = datetime(2026, 8, 31, 16, 0, tzinfo=timezone.utc)
    jid = enqueue_schedule_run(JobRepository(db), schedule_id=3, now=now)
    params = JobRepository(db).get(jid).params
    assert params["slot_day"] == "2026-08-31"
    assert params["slot_when"].startswith("2026-08-31T16:00:00")
    assert "master:3:2026-08-31" in params["slot_id"] or "personal:3:2026-08-31" in params["slot_id"]


def test_parse_scheduled_slot_id_round_trip():
    slot = scheduled_slot_id(
        schedule_type="personal", schedule_id=9, slot_day="2026-08-31",
        catch_up_for_date="2026-08-30", include_regular=False,
    )
    parsed = parse_scheduled_slot_id(slot)
    assert parsed == {
        "schedule_type": "personal", "schedule_id": 9, "slot_day": "2026-08-31",
        "catch_up_for_date": "2026-08-30", "include_regular": False,
    }
    assert parse_scheduled_slot_id("manual:abc") is None


def test_empty_skip_does_not_mark_workbook_email_sent(tmp_path):
    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="email", target="a@x.com")
    assert legs.get(key) is None
    # prepare is not called when execute sees skipped_empty
    from web.delivery.execute import deliver_with_legs
    from web.delivery.service import PreparedWorkbook

    class FakeDelivery:
        email = EmailService(
            _cfg(tmp_path), OutboxRepository(db), SharePointService(_cfg(tmp_path)))

        def prepare(self, **kwargs):
            return PreparedWorkbook(
                row_count=0, xlsx=None, filename="", folder="",
                skipped_empty=True, skip_reason="No data — skipped.",
            )

    out = deliver_with_legs(
        FakeDelivery(), legs, slot_id="s1", job_id="j", run_id=1,
        window={}, recipients="a@x.com", sharepoint_path="",
        report_key="ordered", identity="u@x.com", builder_version=1,
    )
    assert out.row_count == 0
    assert legs.get(key) is None


def test_failed_notice_stays_failed_and_retryable(tmp_path):
    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="notice", target="a@x.com", salesman="MKolko")
    legs.prepare(key, run_id=1, kind="notice", target="a@x.com",
                 salesman_key="MKolko", slot_id="s1", job_id="j")
    legs.mark_sending(key)
    legs.mark_failed(key, "Graph rejected the notice")
    assert legs.get(key).status == FAILED
    assert not legs.is_settled(key)
    assert legs.reopen_for_retry(key) is True


def test_unknown_is_not_auto_retried(tmp_path):
    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com", slot_id="s1")
    legs.mark_sending(key)
    legs.mark_unknown(key, "lost after submit")
    assert legs.prepare(key, run_id=1, kind="email", target="a@x.com") == "skip"
    assert legs.get(key).status == UNKNOWN


def test_partial_fan_out_keeps_sent_and_failed(tmp_path):
    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    sent = attempt_key(slot_id="s1", kind="email", target="a@x.com", salesman="A")
    failed = attempt_key(slot_id="s1", kind="email", target="b@x.com", salesman="B")
    legs.prepare(sent, run_id=1, kind="email", target="a@x.com", salesman_key="A", slot_id="s1")
    legs.mark_sending(sent)
    legs.mark_accepted(sent)
    legs.mark_sent(sent, row_count=4)
    legs.prepare(failed, run_id=1, kind="email", target="b@x.com", salesman_key="B", slot_id="s1")
    legs.mark_sending(failed)
    legs.mark_failed(failed, "Graph HTTP 400")
    assert legs.get(sent).status == SENT
    assert legs.get(failed).status == FAILED
    assert legs.prepare(sent, run_id=1, kind="email", target="a@x.com", salesman_key="A") == "skip"
    assert legs.prepare(failed, run_id=1, kind="email", target="b@x.com", salesman_key="B") == "send"


def test_operator_mark_sent_and_retry(tmp_path):
    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com", slot_id="s1")
    legs.mark_sending(key)
    legs.mark_unknown(key, "lost")
    legs.mark_sent(key, row_count=3)
    assert legs.get(key).status == SENT
    key2 = attempt_key(slot_id="s2", kind="email", target="b@x.com")
    legs.prepare(key2, run_id=1, kind="email", target="b@x.com", slot_id="s2")
    legs.mark_sending(key2)
    legs.mark_unknown(key2, "lost")
    assert legs.reopen_for_retry(key2) is True
    assert legs.get(key2).status == PREPARED


def test_operator_retry_reuses_frozen_slot_after_midnight(tmp_path):
    db = _db(tmp_path)
    jobs = JobRepository(db)
    slot = scheduled_slot_id(
        schedule_type="personal", schedule_id=3, slot_day="2026-08-31")
    jid = jobs.enqueue("schedule.run", params={
        "schedule_id": 3, "schedule_type": "personal",
        "slot_id": slot, "slot_day": "2026-08-31",
        "include_regular": True, "catch_up_for_date": "",
    })
    jobs.claim_next()
    jobs.recover_orphans()
    assert jobs.get(jid).status == "cancelled"
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id=slot, kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com", job_id=jid, slot_id=slot)
    legs.mark_sending(key)
    legs.mark_unknown(key, "lost")
    assert legs.reopen_for_retry(key) is True
    new_id = enqueue_leg_retry(jobs, legs.get(key))
    assert new_id
    params = jobs.get(new_id).params
    assert params["slot_id"] == slot
    assert params["slot_day"] == "2026-08-31"
    assert params["retry_attempt_key"] == key
    assert attempt_key(
        slot_id=params["slot_id"], kind="email", target="a@x.com") == key


def test_operator_retry_parses_clock_slot_when_job_is_gone(tmp_path):
    db = _db(tmp_path)
    jobs = JobRepository(db)
    slot = scheduled_slot_id(
        schedule_type="personal", schedule_id=8, slot_day="2026-08-31",
        catch_up_for_date="2026-08-30", include_regular=False,
    )
    frozen = "2026-08-31T13:00:00-04:00"
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id=slot, kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com",
                 job_id="deleted-job", slot_id=slot, slot_when=frozen)
    legs.prepare(key, run_id=1, kind="email", target="a@x.com",
                 job_id="deleted-job", slot_id=slot)
    assert legs.get(key).slot_when == frozen
    legs.mark_sending(key)
    legs.mark_unknown(key, "lost")
    assert legs.reopen_for_retry(key) is True
    new_id = enqueue_leg_retry(jobs, legs.get(key))
    assert new_id
    params = jobs.get(new_id).params
    assert params["slot_id"] == slot
    assert params["slot_day"] == "2026-08-31"
    assert params["slot_when"] == frozen
    assert params["catch_up_for_date"] == "2026-08-30"
    assert params["include_regular"] is False
    assert params["retry_attempt_key"] == key


def test_job_gone_retry_empty_slot_when_uses_midnight_eastern(tmp_path):
    from web.delivery.filename_template import parse_frozen_when

    db = _db(tmp_path)
    jobs = JobRepository(db)
    slot = scheduled_slot_id(
        schedule_type="personal", schedule_id=8, slot_day="2026-08-31")
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id=slot, kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com",
                 job_id="deleted-job", slot_id=slot)
    legs.mark_sending(key)
    legs.mark_unknown(key, "lost")
    assert legs.reopen_for_retry(key) is True
    new_id = enqueue_leg_retry(jobs, legs.get(key))
    params = jobs.get(new_id).params
    expected = parse_frozen_when("", "2026-08-31").isoformat()
    assert params["slot_when"] == expected


class _Ok:
    def read(self):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_graph_timeout_after_submit_is_unknown(monkeypatch):
    mailer = GraphMailer("tid", "cid", "secret")
    monkeypatch.setattr(mailer, "_token", lambda: "tok")

    def boom(req, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr("web.delivery.graph_mail.urllib.request.urlopen", boom)
    with pytest.raises(GraphUnknownError):
        mailer.send(sender="from@x.com", to=["a@x.com"], subject="Hi", body_text="x")


def test_graph_connection_refused_is_failed_not_unknown(monkeypatch):
    mailer = GraphMailer("tid", "cid", "secret")
    monkeypatch.setattr(mailer, "_token", lambda: "tok")

    def boom(req, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr("web.delivery.graph_mail.urllib.request.urlopen", boom)
    with pytest.raises(GraphMailError) as ei:
        mailer.send(sender="from@x.com", to=["a@x.com"], subject="Hi", body_text="x")
    assert not isinstance(ei.value, GraphUnknownError)


def test_graph_401_clears_token_and_retries_once(monkeypatch):
    mailer = GraphMailer("tid", "cid", "secret")
    monkeypatch.setattr(mailer, "_token", lambda: "tok")
    cleared = []
    monkeypatch.setattr(mailer._tokens, "clear", lambda: cleared.append(1))
    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                req.full_url, 401, "no", {}, io.BytesIO(b"expired"),
            )
        return _Ok()

    monkeypatch.setattr("web.delivery.graph_mail.urllib.request.urlopen", fake_urlopen)
    mailer.send(sender="from@x.com", to=["a@x.com"], subject="Hi", body_text="x")
    assert calls["n"] == 2
    assert cleared == [1]


def test_email_deliver_records_unknown(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, tenant_id="t", client_id="c", client_secret="s",
               email_from="from@x.com")
    db = _db(tmp_path)
    graph = GraphMailer("t", "c", "s")
    monkeypatch.setattr(graph, "send", lambda **k: (_ for _ in ()).throw(
        GraphUnknownError("lost after submit")))
    svc = EmailService(cfg, OutboxRepository(db), SharePointService(cfg), graph=graph)
    res = svc.deliver(subject="S", recipients_raw="a@x.com", body_text="hi",
                      report_name="Ordered")
    assert res.unknown is True
    assert res.ok is False
    assert "lost" in res.error.lower() or "connection" in res.error.lower()


def test_legs_prune_old_rows(tmp_path):
    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="old", kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com", slot_id="old")
    with db.precious() as conn:
        conn.execute(
            "UPDATE delivery_legs SET updated_at=datetime('now', '-100 days')"
            " WHERE attempt_key=?",
            (key,),
        )
    assert legs.prune(older_than_days=90) == 1
    assert legs.get(key) is None


def test_cancel_after_build_before_send_does_not_create_sending_leg(tmp_path):
    from web.delivery.execute import deliver_with_legs
    from web.delivery.service import PreparedWorkbook
    from web.jobs.worker import JobCancelled

    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    built = {"n": 0}

    class FakeDelivery:
        email = EmailService(
            _cfg(tmp_path), OutboxRepository(db), SharePointService(_cfg(tmp_path)))

        def prepare(self, **kwargs):
            built["n"] += 1
            return PreparedWorkbook(
                row_count=1, xlsx=b"PK", filename="r.xlsx", folder="")

    with pytest.raises(JobCancelled):
        deliver_with_legs(
            FakeDelivery(), legs, slot_id="s1", job_id="j", run_id=1,
            window={}, recipients="a@x.com", sharepoint_path="",
            report_key="ordered", identity="u@x.com", builder_version=1,
            cancel_check=lambda: built["n"] > 0,
        )
    assert built["n"] == 1
    key = attempt_key(slot_id="s1", kind="email", target="a@x.com")
    assert legs.get(key) is None


def test_cancel_during_send_marks_failed_not_sent(tmp_path):
    from web.delivery.execute import _send_email_leg
    from web.delivery.service import PreparedWorkbook
    from web.jobs.worker import JobCancelled

    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="email", target="a@x.com")
    built = PreparedWorkbook(row_count=2, xlsx=b"PK", filename="r.xlsx", folder="")

    class BoomEmail:
        def deliver(self, **kwargs):
            raise JobCancelled()

    class D:
        email = BoomEmail()

    with pytest.raises(JobCancelled):
        _send_email_leg(
            D(), legs, key, built, subject="S", report_name="R", body_text="",
            recipients="a@x.com", cc="", bcc="", folder_url="",
            run_id=1, slot_id="s1", job_id="j", salesman="",
            cancel_check=None,
        )
    assert legs.get(key).status == FAILED
    assert legs.get(key).status != SENT


def test_crash_after_folder_accepted_commits_sent(tmp_path):
    db = _db(tmp_path)
    jobs = JobRepository(db)
    jid = jobs.enqueue("schedule.run")
    jobs.claim_next()
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="sharepoint", target="Ordered")
    legs.prepare(key, run_id=1, kind="sharepoint", target="Ordered",
                 job_id=jid, slot_id="s1")
    legs.mark_sending(key)
    legs.mark_accepted(key, remote_id="https://sp/file.xlsx")
    jobs.recover_orphans()
    assert legs.get(key).status == SENT


def test_crash_while_folder_sending_is_failed_retryable(tmp_path):
    db = _db(tmp_path)
    jobs = JobRepository(db)
    jid = jobs.enqueue("schedule.run")
    jobs.claim_next()
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="sharepoint", target="Ordered")
    legs.prepare(key, run_id=1, kind="sharepoint", target="Ordered",
                 job_id=jid, slot_id="s1")
    legs.mark_sending(key)
    jobs.recover_orphans()
    assert legs.get(key).status == FAILED
    assert "folder" in legs.get(key).error.lower() or "upload" in legs.get(key).error.lower()
    assert legs.reopen_for_retry(key) is True


def test_folder_upload_error_then_get_is_sent(tmp_path):
    from web.delivery.execute import _send_folder_leg
    from web.delivery.service import PreparedWorkbook

    class SP:
        def upload_file(self, *a, **k):
            raise RuntimeError("lost after put")

        def get_file(self, folder, filename):
            return {"webUrl": "https://sp/file.xlsx"}

    class D:
        email = type("E", (), {"sharepoint": SP(), "onedrive": None})()

    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="sharepoint", target="Ordered")
    built = PreparedWorkbook(row_count=1, xlsx=b"PK", filename="r.xlsx", folder="Ordered")
    res = _send_folder_leg(
        D(), legs, key, built, onedrive_user="", run_id=1,
        slot_id="s1", job_id="j", salesman="", cancel_check=None,
    )
    assert res.ok and res.sharepoint_saved
    assert legs.get(key).status == SENT
    assert legs.get(key).remote_id == "https://sp/file.xlsx"


def test_reconcile_retry_http_reuses_slot_and_rejects_salesman(tmp_path):
    from tests.test_blueprints import _CSRF, _login, _make_app

    app = _make_app(tmp_path)
    client = app.test_client()
    db = app.config["DB"]
    uid = UserRepository(db).upsert("admin@x.com", display_name="Admin", role="admin").id
    sid = ScheduleRepository(db).create(
        uid, "ordered", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="a@x.com")
    run_id = ScheduleRunRepository(db).start(sid, PERSONAL, trigger="scheduled")
    slot = scheduled_slot_id(
        schedule_type="personal", schedule_id=sid, slot_day="2026-08-31")
    jobs = JobRepository(db)
    jid = jobs.enqueue("schedule.run", owner_user_id=uid, params={
        "schedule_id": sid, "schedule_type": "personal",
        "slot_id": slot, "slot_day": "2026-08-31",
        "include_regular": True, "catch_up_for_date": "",
    })
    jobs.claim_next()
    jobs.mark_success(jid, "run:1")
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id=slot, kind="email", target="a@x.com")
    legs.prepare(key, run_id=run_id, kind="email", target="a@x.com",
                 job_id=jid, slot_id=slot)
    legs.mark_sending(key)
    legs.mark_unknown(key, "lost")

    _login(client, app, email="rep@x.com", role="salesman")
    denied = client.post(
        f"/api/delivery-legs/{key}/reconcile",
        data={"action": "retry", "csrf_token": _CSRF},
    )
    assert denied.status_code == 403
    assert legs.get(key).status == UNKNOWN

    _login(client, app, email="mgr@x.com", role="manager")
    denied_mgr = client.post(
        f"/api/delivery-legs/{key}/reconcile",
        data={"action": "retry", "csrf_token": _CSRF},
    )
    assert denied_mgr.status_code == 403

    _login(client, app)
    ok = client.post(
        f"/api/delivery-legs/{key}/reconcile",
        data={"action": "retry", "csrf_token": _CSRF},
    )
    assert ok.status_code == 200
    assert legs.get(key).status == PREPARED
    queued = [
        j for j in jobs.list_for_user(uid, limit=20)
        if j.status == "queued" and j.params.get("slot_id") == slot
    ]
    assert len(queued) == 1
    assert queued[0].params["slot_day"] == "2026-08-31"


def test_reconcile_retry_two_legs_same_slot_queues_two_jobs(tmp_path):
    from tests.test_blueprints import _CSRF, _login, _make_app

    app = _make_app(tmp_path)
    client = app.test_client()
    db = app.config["DB"]
    uid = UserRepository(db).upsert("admin@x.com", display_name="Admin", role="admin").id
    sid = ScheduleRepository(db).create(
        uid, "ordered", params={}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="a@x.com")
    run_id = ScheduleRunRepository(db).start(sid, PERSONAL, trigger="scheduled")
    slot = scheduled_slot_id(
        schedule_type="personal", schedule_id=sid, slot_day="2026-08-31")
    jobs = JobRepository(db)
    jid = jobs.enqueue("schedule.run", owner_user_id=uid, params={
        "schedule_id": sid, "schedule_type": "personal",
        "slot_id": slot, "slot_day": "2026-08-31",
        "include_regular": True, "catch_up_for_date": "",
    })
    jobs.claim_next()
    jobs.mark_success(jid, "run:1")
    legs = DeliveryLegRepository(db)
    key_a = attempt_key(slot_id=slot, kind="email", target="a@x.com", salesman="A")
    key_b = attempt_key(slot_id=slot, kind="email", target="b@x.com", salesman="B")
    for key, target, salesman in (
        (key_a, "a@x.com", "A"),
        (key_b, "b@x.com", "B"),
    ):
        legs.prepare(key, run_id=run_id, kind="email", target=target,
                     salesman_key=salesman, job_id=jid, slot_id=slot)
        legs.mark_sending(key)
        legs.mark_unknown(key, "lost")

    _login(client, app)
    first = client.post(
        f"/api/delivery-legs/{key_a}/reconcile",
        data={"action": "retry", "csrf_token": _CSRF},
    )
    second = client.post(
        f"/api/delivery-legs/{key_b}/reconcile",
        data={"action": "retry", "csrf_token": _CSRF},
    )
    assert first.status_code == 200 and second.status_code == 200
    assert legs.get(key_a).status == PREPARED
    assert legs.get(key_b).status == PREPARED
    queued = [
        j for j in jobs.list_for_user(uid, limit=20)
        if j.status == "queued" and j.params.get("slot_id") == slot
    ]
    keys = {j.params.get("retry_attempt_key") for j in queued}
    assert keys == {key_a, key_b}
    assert len(queued) == 2
    same = enqueue_leg_retry(jobs, legs.get(key_a))
    assert same in {j.id for j in queued}
    still = [
        j for j in jobs.list_for_user(uid, limit=20)
        if j.status == "queued" and j.params.get("slot_id") == slot
    ]
    assert len(still) == 2


def test_graph_token_refreshes_before_expiry(monkeypatch):
    from web.delivery.graph_token import GraphTokenCache

    n = {"i": 0}

    def acquire(self):
        n["i"] += 1
        return f"tok{n['i']}", 120

    monkeypatch.setattr(GraphTokenCache, "_acquire", acquire)
    cache = GraphTokenCache("t", "c", "s")
    monkeypatch.setattr("web.delivery.graph_token.time.time", lambda: 1000.0)
    assert cache.get() == "tok1"
    monkeypatch.setattr("web.delivery.graph_token.time.time", lambda: 1050.0)
    assert cache.get() == "tok1"
    monkeypatch.setattr("web.delivery.graph_token.time.time", lambda: 1070.0)
    assert cache.get() == "tok2"
    cache.clear()
    assert cache.get() == "tok3"


def _workbook_delivery(sent=None, puts=None, files=None, folder="Ordered"):
    from web.delivery.email import DeliveryResult
    from web.delivery.service import PreparedWorkbook

    sent = sent if sent is not None else []
    puts = puts if puts is not None else []
    files = files if files is not None else {}

    class SP:
        def get_file(self, folder_name, filename):
            return files.get((folder_name, filename))

        def upload_file(self, folder_name, filename, data, resume_url="", on_session=None):
            puts.append({"folder": folder_name, "filename": filename, "resume": resume_url})
            if on_session:
                on_session("https://upload/session")
            return {"webUrl": "https://sp/" + filename}

    class Mail:
        sharepoint = SP()
        onedrive = None

        def deliver(self, **kwargs):
            sent.append(kwargs.get("recipients_raw"))
            return DeliveryResult(ok=True, recipients=[kwargs.get("recipients_raw") or ""])

    class Delivery:
        email = Mail()

        def prepare(self, **kwargs):
            from web.delivery.filename_template import resolve_filename_template, resolve_folder_template
            when = kwargs.get("when")
            name = resolve_filename_template(
                kwargs.get("filename_template") or "",
                report_name=kwargs.get("report_name") or "R",
                when=when,
            )
            resolved = resolve_folder_template(
                kwargs.get("sharepoint_path") or folder,
                report_name=kwargs.get("report_name") or "R",
                when=when,
            )
            return PreparedWorkbook(
                row_count=1, xlsx=b"PK", filename=name, folder=resolved or folder,
            )

    return Delivery(), sent, puts, files


def test_retry_sends_only_the_selected_attempt_and_frozen_target(tmp_path):
    from web.delivery.execute import deliver_with_legs

    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    key_a = attempt_key(slot_id="s1", kind="email", target="a@x.com", salesman="A")
    key_b = attempt_key(slot_id="s1", kind="email", target="b@x.com", salesman="B")
    legs.prepare(key_b, run_id=1, kind="email", target="b@x.com",
                 salesman_key="B", slot_id="s1", job_id="j")
    legs.mark_failed(key_b, "lost")
    assert legs.reopen_for_retry(key_b)
    delivery, sent, _puts, _files = _workbook_delivery()
    common = dict(
        slot_id="s1", job_id="j", run_id=1, window={},
        report_key="ordered", identity="u@x.com", builder_version=1,
        retry_attempt_key=key_b,
    )
    deliver_with_legs(delivery, legs, salesman="A", recipients="a@x.com", **common)
    deliver_with_legs(
        delivery, legs, salesman="B", recipients="new-b@x.com", **common,
    )
    assert sent == ["b@x.com"]
    assert legs.get(key_a) is None
    assert legs.get(key_b).status == SENT


def _fanout_retry_runner(db, delivery):
    from web.auth.authorization import Authorization
    from web.data.repositories.schedules import (
        MasterScheduleRepository, ScheduleRepository, ScheduleRunRepository,
    )
    from web.scheduling.runner import ScheduleRunner

    return ScheduleRunner(
        schedule_repo=ScheduleRepository(db),
        master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=Authorization(db), delivery=delivery,
    )


def test_fanout_retry_sends_stored_target_when_live_email_blank(tmp_path):
    from web.data.repositories.salesmen import SalesmanRepository, SalesmanSeed
    from web.data.repositories.schedules import MASTER, MasterScheduleRepository

    db = _db(tmp_path)
    SalesmanRepository(db).upsert_many([
        SalesmanSeed(raw_key="A", number="1", full_name="A", display_name="A",
                     email="stored@example.com"),
    ])
    masters = MasterScheduleRepository(db)
    mid = masters.create(
        "ordered", "Nightly", params={"email_salesman_keys": ["A"]},
        layout={}, cadence={"freq": "daily", "time": "08:00"},
        recipients="manager@x.com")
    sched = masters.get(mid)
    key = attempt_key(
        slot_id="s1", kind="email", target="stored@example.com", salesman="A")
    legs = DeliveryLegRepository(db)
    legs.prepare(key, run_id=1, kind="email", target="stored@example.com",
                 salesman_key="A", slot_id="s1", job_id="j")
    legs.mark_sending(key)
    legs.mark_unknown(key, "lost")
    assert legs.reopen_for_retry(key)
    SalesmanRepository(db).upsert_many([
        SalesmanSeed(raw_key="A", number="1", full_name="A", display_name="A", email=""),
    ])
    delivery, sent, _puts, _files = _workbook_delivery()
    out = _fanout_retry_runner(db, delivery)._run_master_fanout(
        sched=sched, identity="u@x.com", scope=None, builder_version=1,
        subject="S", report_name="R", onedrive_user="", test_to=None,
        params={"email_salesman_keys": ["A"]}, schedule_name="N",
        cancel_check=None, run_id=1, trigger="manual",
        schedule_type=MASTER, schedule_id=mid,
        slot_id="s1", job_id="j", when=None, retry_attempt_key=key,
    )
    assert out.result.ok
    assert sent == ["stored@example.com"]
    assert legs.get(key).status == SENT


def test_fanout_retry_sends_stored_target_when_salesman_dropped(tmp_path):
    from web.data.repositories.salesmen import SalesmanRepository, SalesmanSeed
    from web.data.repositories.schedules import MASTER, MasterScheduleRepository

    db = _db(tmp_path)
    SalesmanRepository(db).upsert_many([
        SalesmanSeed(raw_key="A", number="1", full_name="A", display_name="A",
                     email="stored@example.com"),
    ])
    masters = MasterScheduleRepository(db)
    mid = masters.create(
        "ordered", "Nightly", params={"email_salesman_keys": ["B"]},
        layout={}, cadence={"freq": "daily", "time": "08:00"},
        recipients="manager@x.com")
    sched = masters.get(mid)
    key = attempt_key(
        slot_id="s1", kind="email", target="stored@example.com", salesman="A")
    legs = DeliveryLegRepository(db)
    legs.prepare(key, run_id=1, kind="email", target="stored@example.com",
                 salesman_key="A", slot_id="s1", job_id="j")
    legs.mark_sending(key)
    legs.mark_unknown(key, "lost")
    assert legs.reopen_for_retry(key)
    delivery, sent, _puts, _files = _workbook_delivery()
    out = _fanout_retry_runner(db, delivery)._run_master_fanout(
        sched=sched, identity="u@x.com", scope=None, builder_version=1,
        subject="S", report_name="R", onedrive_user="", test_to=None,
        params={"email_salesman_keys": ["B"]}, schedule_name="N",
        cancel_check=None, run_id=1, trigger="manual",
        schedule_type=MASTER, schedule_id=mid,
        slot_id="s1", job_id="j", when=None, retry_attempt_key=key,
    )
    assert out.result.ok
    assert sent == ["stored@example.com"]
    assert "Salesman" not in (out.result.error or "")
    assert legs.get(key).status == SENT


def test_folder_verify_uses_frozen_when_not_live_clock(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from web.delivery.execute import deliver_with_legs
    from web.delivery.filename_template import resolve_filename_template, resolve_folder_template

    t1 = datetime(2026, 8, 31, 13, 0, tzinfo=ZoneInfo("America/New_York"))
    t2 = datetime(2026, 9, 1, 9, 5, tzinfo=ZoneInfo("America/New_York"))
    name1 = resolve_filename_template("", report_name="R", when=t1)
    name2 = resolve_filename_template("", report_name="R", when=t2)
    assert name1 != name2
    folder1 = resolve_folder_template("{Month}", report_name="R", when=t1)
    assert folder1 == "August"
    files = {(folder1, name1): {"webUrl": "https://sp/original"}}
    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    delivery, _sent, puts, _files = _workbook_delivery(files=files, folder="{Month}")
    out = deliver_with_legs(
        delivery, legs, slot_id="s1", job_id="j", run_id=1, window={},
        recipients="", sharepoint_path="{Month}",
        report_key="ordered", identity="u@x.com", builder_version=1,
        filename_template="", report_name="R", when=t1,
    )
    assert out.result.ok and not puts
    key = attempt_key(slot_id="s1", kind="sharepoint", target="August")
    assert legs.get(key).status == SENT
    assert legs.get(key).remote_id == "https://sp/original"


def test_job_gone_retry_folder_keeps_frozen_filename(tmp_path):
    from web.delivery.execute import deliver_with_legs
    from web.delivery.filename_template import parse_frozen_when, resolve_filename_template

    frozen = "2026-08-31T13:00:00-04:00"
    when = parse_frozen_when(frozen, "2026-08-31")
    name = resolve_filename_template("", report_name="R", when=when)
    assert name == "R_2026-08-31_1300.xlsx"
    files = {("Ordered", name): {"webUrl": "https://sp/original"}}
    db = _db(tmp_path)
    jobs = JobRepository(db)
    slot = scheduled_slot_id(
        schedule_type="personal", schedule_id=8, slot_day="2026-08-31")
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id=slot, kind="sharepoint", target="Ordered")
    legs.prepare(key, run_id=1, kind="sharepoint", target="Ordered",
                 job_id="deleted-job", slot_id=slot, slot_when=frozen)
    legs.mark_sending(key)
    legs.mark_failed(key, "interrupted")
    assert legs.reopen_for_retry(key) is True
    new_id = enqueue_leg_retry(jobs, legs.get(key))
    params = jobs.get(new_id).params
    assert params["slot_when"] == frozen
    retry_when = parse_frozen_when(params["slot_when"], params["slot_day"])
    delivery, _sent, puts, _files = _workbook_delivery(files=files, folder="Ordered")
    out = deliver_with_legs(
        delivery, legs, slot_id=slot, job_id=new_id, run_id=1, window={},
        recipients="", sharepoint_path="Ordered",
        report_key="ordered", identity="u@x.com", builder_version=1,
        filename_template="", report_name="R",
        when=retry_when, retry_attempt_key=key,
    )
    assert out.result.ok
    assert puts == []
    assert legs.get(key).status == SENT
    assert legs.get(key).remote_id == "https://sp/original"


def test_retry_after_period_change_still_sends_selected_leg(tmp_path):
    from web.delivery.execute import deliver_with_legs

    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    original = {"period": "yesterday"}
    key = attempt_key(slot_id="s1", kind="email", target="a@x.com", window=original)
    legs.prepare(key, run_id=1, kind="email", target="a@x.com",
                 slot_id="s1", job_id="j", window_from="yesterday")
    legs.mark_sending(key)
    legs.mark_unknown(key, "lost")
    assert legs.reopen_for_retry(key) is True
    delivery, sent, _puts, _files = _workbook_delivery()
    out = deliver_with_legs(
        delivery, legs, slot_id="s1", job_id="j", run_id=1,
        window={"period": "mtd"}, params={"period": "mtd"},
        recipients="a@x.com", sharepoint_path="",
        report_key="ordered", identity="u@x.com", builder_version=1,
        retry_attempt_key=key,
    )
    assert out.result.ok
    assert sent == ["a@x.com"]
    assert legs.get(key).status == SENT


def test_retry_after_filename_template_change_gets_original_name(tmp_path):
    from web.delivery.execute import deliver_with_legs
    from web.delivery.filename_template import parse_frozen_when

    frozen = "2026-08-31T13:00:00-04:00"
    original = "R_2026-08-31_1300.xlsx"
    files = {("Ordered", original): {"webUrl": "https://sp/original"}}
    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="sharepoint", target="Ordered")
    legs.prepare(key, run_id=1, kind="sharepoint", target="Ordered",
                 slot_id="s1", job_id="j", slot_when=frozen, filename=original)
    legs.mark_sending(key)
    legs.mark_failed(key, "interrupted")
    assert legs.reopen_for_retry(key) is True
    delivery, _sent, puts, _files = _workbook_delivery(files=files, folder="Ordered")
    out = deliver_with_legs(
        delivery, legs, slot_id="s1", job_id="j", run_id=1, window={},
        recipients="", sharepoint_path="Ordered",
        report_key="ordered", identity="u@x.com", builder_version=1,
        filename_template="Changed_{YYYY}-{MM}-{DD}_{HH}{mm}", report_name="R",
        when=parse_frozen_when(frozen, "2026-08-31"), retry_attempt_key=key,
    )
    assert out.result.ok
    assert puts == []
    assert legs.get(key).status == SENT
    assert legs.get(key).remote_id == "https://sp/original"
    assert legs.get(key).filename == original


def test_first_send_stores_window_and_filename(tmp_path):
    from web.delivery.execute import deliver_with_legs
    from web.delivery.filename_template import parse_frozen_when, resolve_filename_template

    frozen = "2026-08-31T13:00:00-04:00"
    when = parse_frozen_when(frozen, "2026-08-31")
    name = resolve_filename_template("", report_name="R", when=when)
    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    delivery, sent, _puts, _files = _workbook_delivery()
    deliver_with_legs(
        delivery, legs, slot_id="s1", job_id="j", run_id=1,
        window={"period": "yesterday"}, params={"period": "yesterday"},
        recipients="a@x.com", sharepoint_path="Ordered",
        report_key="ordered", identity="u@x.com", builder_version=1,
        filename_template="", report_name="R", when=when,
    )
    email_key = attempt_key(
        slot_id="s1", kind="email", target="a@x.com", window={"period": "yesterday"})
    folder_key = attempt_key(
        slot_id="s1", kind="sharepoint", target="Ordered", window={"period": "yesterday"})
    assert sent == ["a@x.com"]
    assert legs.get(email_key).window_from == "yesterday"
    assert legs.get(email_key).filename == name
    assert legs.get(folder_key).window_from == "yesterday"
    assert legs.get(folder_key).filename == name


def test_reopen_for_retry_keeps_upload_session(tmp_path):
    from web.delivery.execute import _send_folder_leg
    from web.delivery.service import PreparedWorkbook

    db = _db(tmp_path)
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id="s1", kind="sharepoint", target="Ordered")
    legs.prepare(key, run_id=1, kind="sharepoint", target="Ordered",
                 slot_id="s1", job_id="j")
    legs.mark_sending(key)
    legs.set_upload_session(key, "https://upload/session")
    legs.mark_failed(key, "lost")
    assert legs.reopen_for_retry(key) is True
    assert legs.get(key).upload_session_url == "https://upload/session"

    seen = {}

    class SP:
        def get_file(self, folder, filename):
            return None

        def upload_file(self, folder, filename, data, resume_url="", on_session=None):
            seen["resume"] = resume_url
            return {"webUrl": "https://sp/file.xlsx"}

    class D:
        email = type("E", (), {"sharepoint": SP(), "onedrive": None})()

    built = PreparedWorkbook(row_count=1, xlsx=b"PK", filename="r.xlsx", folder="Ordered")
    _send_folder_leg(
        D(), legs, key, built, onedrive_user="", run_id=1,
        slot_id="s1", job_id="j", salesman="", cancel_check=None,
    )
    assert seen["resume"] == "https://upload/session"


def test_email_now_unknown_alert_includes_attempt_key(tmp_path):
    from web.data.repositories.app_settings import AppSettingsRepository
    from web.data.repositories.notifications import NotificationRepository
    from web.delivery.reconcile import alert_unknown_delivery

    db = _db(tmp_path)
    uid = UserRepository(db).upsert("admin@x.com", display_name="Admin", role="admin").id
    settings = AppSettingsRepository(db)
    settings.set_schedule_test(emails=["ops@x.com"])
    key = attempt_key(slot_id="manual-deliver:1", kind="email", target="a@x.com")
    DeliveryLegRepository(db).prepare(
        key, run_id=None, kind="email", target="a@x.com",
        slot_id="manual-deliver:1", job_id="j1",
    )
    DeliveryLegRepository(db).mark_unknown(key, "lost after submit")
    notices = []

    class Mail:
        def send_notice(self, **kwargs):
            notices.append(kwargs)

    delivery = type("D", (), {"email": Mail()})()
    alert_unknown_delivery(
        db, AppSettingsRepository(db), delivery=delivery,
        subject="[UNKNOWN] email-now send", body="Graph may have accepted this send.",
        attempt_key=key,
    )
    assert key in notices[0]["body_text"]
    payload = NotificationRepository(db).list_undismissed(uid)[0].payload
    assert payload["attempt_key"] == key


def test_schedules_page_lists_unattached_unknown_for_admin_not_salesman(tmp_path):
    from tests.test_blueprints import _CSRF, _login, _make_app

    app = _make_app(tmp_path)
    client = app.test_client()
    db = app.config["DB"]
    UserRepository(db).upsert("admin@x.com", display_name="Admin", role="admin")
    key = attempt_key(slot_id="manual-deliver:9", kind="email", target="a@x.com")
    legs = DeliveryLegRepository(db)
    legs.prepare(key, run_id=None, kind="email", target="a@x.com",
                 slot_id="manual-deliver:9", job_id="j9")
    legs.mark_unknown(key, "lost")

    _login(client, app, email="rep@x.com", role="salesman")
    hidden = client.get("/schedules")
    assert hidden.status_code == 200
    assert b"Unknown email-now sends" not in hidden.data
    assert key.encode() not in hidden.data

    _login(client, app)
    shown = client.get("/schedules")
    assert shown.status_code == 200
    assert b"Unknown email-now sends" in shown.data
    assert key.encode() in shown.data
    mark = client.post(
        f"/api/delivery-legs/{key}/reconcile",
        data={"action": "mark_sent", "csrf_token": _CSRF, "next": "/schedules"},
    )
    assert mark.status_code == 302
    assert legs.get(key).status == SENT
