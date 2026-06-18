"""Data layer: migrations, foreign keys, durable job queue, user repo."""

import sqlite3
import threading

import pytest

from web.data.connection import Database, _connect
from web.data.migrate import apply_migrations, migrate
from web.data.repositories.jobs import JobRepository
from web.data.repositories.users import UserRepository


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "precious.db", tmp_path / "cache.db")
    migrate(d)
    return d


def test_migrations_are_idempotent(tmp_path):
    d = Database(tmp_path / "p.db", tmp_path / "c.db")
    first = migrate(d)
    assert "0001_initial" in first["precious"]
    assert "0001_initial" in first["cache"]
    second = migrate(d)  # re-run: nothing new
    assert second == {"precious": [], "cache": []}


def test_foreign_keys_enforced(db):
    # Inserting a child row with no parent user must fail (FK ON).
    with pytest.raises(sqlite3.IntegrityError):
        with db.precious() as conn:
            conn.execute(
                "INSERT INTO notifications(user_id, type) VALUES (?, ?)", (999, "x")
            )


def test_journal_mode_defaults_to_wal(tmp_path, monkeypatch):
    monkeypatch.delenv("SQLITE_JOURNAL_MODE", raising=False)
    conn = _connect(tmp_path / "p.db")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_journal_mode_override_for_smb(tmp_path, monkeypatch):
    # On an Azure Files/SMB share WAL can't share its index across processes, so
    # we open in a rollback journal (file-locked, works over SMB) instead.
    monkeypatch.setenv("SQLITE_JOURNAL_MODE", "TRUNCATE")
    conn = _connect(tmp_path / "p.db")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "truncate"
    finally:
        conn.close()


def test_journal_mode_ignores_unknown_value(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_JOURNAL_MODE", "bogus")
    conn = _connect(tmp_path / "p.db")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


def test_user_upsert_round_trip(db):
    repo = UserRepository(db)
    u = repo.upsert("Test@Example.com ", display_name="Tester", role="admin")
    assert u.email == "test@example.com"
    assert u.role == "admin"
    assert repo.get_by_email("test@example.com").id == u.id


def test_job_queue_lifecycle(db):
    jobs = JobRepository(db)
    jid = jobs.enqueue("report.run", params={"key": "ordered"})
    assert jobs.get(jid).status == "queued"

    claimed = jobs.claim_next()
    assert claimed.id == jid and claimed.status == "running"
    assert jobs.claim_next() is None  # nothing else queued

    jobs.set_progress(jid, 50)
    assert jobs.get(jid).progress == 50

    jobs.mark_success(jid, result_ref="cache:abc")
    done = jobs.get(jid)
    assert done.status == "success" and done.progress == 100 and done.result_ref == "cache:abc"


def test_job_dedup_returns_existing(db):
    jobs = JobRepository(db)
    a = jobs.enqueue("report.run", dedup_key="ordered|u1", params={"k": 1})
    b = jobs.enqueue("report.run", dedup_key="ordered|u1", params={"k": 1})
    assert a == b  # deduped while active

    jobs.claim_next()
    jobs.mark_success(a)
    c = jobs.enqueue("report.run", dedup_key="ordered|u1", params={"k": 1})
    assert c != a  # previous one finished, so a new job is allowed


def test_job_cancel(db):
    jobs = JobRepository(db)
    jid = jobs.enqueue("report.run")
    assert jobs.cancel(jid) is True
    assert jobs.get(jid).status == "cancelled"
    assert jobs.cancel(jid) is False  # already terminal


def test_migration_failure_is_atomic(tmp_path):
    """A failing migration must leave NO schema change and NO version row."""
    mig = tmp_path / "mig"
    mig.mkdir()
    # Creates a table, then references a missing table -> whole file must roll back.
    (mig / "0001_bad.sql").write_text(
        "CREATE TABLE should_not_survive (x INTEGER);\n"
        "INSERT INTO definitely_missing_table (x) VALUES (1);\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "p.db"
    with pytest.raises(sqlite3.OperationalError):
        apply_migrations(db_path, mig)

    conn = _connect(db_path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "should_not_survive" not in tables  # rolled back
        versions = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        assert "0001_bad" not in versions  # not recorded
    finally:
        conn.close()


def test_parallel_workers_can_migrate_the_same_fresh_db(tmp_path):
    """Regression (2026-06-11): gunicorn workers boot in parallel and both ran
    migrate() on a brand-new cache.db; the loser crashed bootstrap with
    'UNIQUE constraint failed: schema_migrations.version'. The loser must
    treat an already-applied version as done, not as a boot failure."""
    d = Database(tmp_path / "p.db", tmp_path / "c.db")
    errors: list[Exception] = []
    barrier = threading.Barrier(4)

    def boot():
        try:
            barrier.wait()
            migrate(d)
        except Exception as exc:  # noqa: BLE001 - the test asserts on these
            errors.append(exc)

    threads = [threading.Thread(target=boot) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == []
    assert migrate(d) == {"precious": [], "cache": []}  # fully applied exactly once


def test_concurrent_enqueue_dedups(db):
    """Many threads enqueueing the same dedup_key produce exactly one active job."""
    jobs = JobRepository(db)
    barrier = threading.Barrier(8)
    results: list[str] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        jid = jobs.enqueue("report.run", dedup_key="same|scope", params={"k": 1})
        with lock:
            results.append(jid)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(results)) == 1  # all got the same job id
    with db.precious() as conn:
        active = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE dedup_key='same|scope' AND status IN ('queued','running')"
        ).fetchone()[0]
        assert active == 1


def test_concurrent_claim_never_double_claims(db):
    """Multiple worker threads draining the queue never claim a job twice."""
    jobs = JobRepository(db)
    ids = {jobs.enqueue("report.run", params={"i": i}) for i in range(12)}

    claimed: list[str] = []
    lock = threading.Lock()

    def drain():
        while True:
            job = jobs.claim_next()
            if job is None:
                # could be contention or empty; retry a couple times then stop
                if all(jobs.get(j).status != "queued" for j in ids):
                    return
                continue
            with lock:
                claimed.append(job.id)

    threads = [threading.Thread(target=drain) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(claimed) == sorted(ids)  # each claimed exactly once
    assert len(claimed) == len(set(claimed))
