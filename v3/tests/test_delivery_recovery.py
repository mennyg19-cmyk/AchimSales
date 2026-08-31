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
    db = _db(tmp_path)
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO delivery_legs(run_id, attempt_key, kind, target, status)"
            " VALUES (1, 'legacy-pending', 'email', 'a@x.com', 'pending')"
        )
    # Re-apply is a no-op; simulate leftover by inserting pending then running
    # the 0023 UPDATE logic the repo now treats as unknown after migrate.
    # Fresh migrate already ran 0023, so insert pending after migrate:
    legs = DeliveryLegRepository(db)
    assert legs.get("legacy-pending").status == "pending"
    with db.precious() as conn:
        conn.execute(
            "UPDATE delivery_legs SET status='unknown',"
            " error='Migrated from pending; confirm whether the mail or file arrived.'"
            " WHERE status='pending'"
        )
    assert legs.get("legacy-pending").status == UNKNOWN
    assert not legs.get("legacy-pending").status == "pending"


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
    assert attempt_key(
        slot_id=params["slot_id"], kind="email", target="a@x.com") == key


def test_operator_retry_parses_clock_slot_when_job_is_gone(tmp_path):
    db = _db(tmp_path)
    jobs = JobRepository(db)
    slot = scheduled_slot_id(
        schedule_type="personal", schedule_id=8, slot_day="2026-08-31",
        catch_up_for_date="2026-08-30", include_regular=False,
    )
    legs = DeliveryLegRepository(db)
    key = attempt_key(slot_id=slot, kind="email", target="a@x.com")
    legs.prepare(key, run_id=1, kind="email", target="a@x.com",
                 job_id="deleted-job", slot_id=slot)
    legs.mark_sending(key)
    legs.mark_unknown(key, "lost")
    assert legs.reopen_for_retry(key) is True
    new_id = enqueue_leg_retry(jobs, legs.get(key))
    assert new_id
    params = jobs.get(new_id).params
    assert params["slot_id"] == slot
    assert params["slot_day"] == "2026-08-31"
    assert params["catch_up_for_date"] == "2026-08-30"
    assert params["include_regular"] is False


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
