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


def test_connection_opens_in_wal(tmp_path):
    # Local-disk SQLite always opens in WAL (what Litestream ships).
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
    assert u.sales_group == ""
    assert repo.get_by_email("test@example.com").id == u.id


def test_sales_group_and_access_without_salesmen_row(db):
    repo = UserRepository(db)
    u = repo.create("rep@x.com", role="salesman", sales_group="HKaufman")
    assert u.sales_group == "HKaufman"
    repo.set_salesman_access(u.id, ["HKaufman"])
    assert repo.get_salesman_access(u.id) == {"hkaufman"}
    with db.precious() as conn:
        fks = conn.execute("PRAGMA foreign_key_list(user_salesman_access)").fetchall()
    tables = {r["table"] for r in fks}
    assert "users" in tables
    assert "salesmen" not in tables


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


def test_duplicate_column_records_version_instead_of_raising(tmp_path):
    """0016 is ALTER ADD COLUMN only. Retry after a lost version row must not crash boot."""
    mig = tmp_path / "mig"
    mig.mkdir()
    db_path = tmp_path / "p.db"
    conn = _connect(db_path)
    try:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
    finally:
        conn.close()
    (mig / "0001_add.sql").write_text(
        "ALTER TABLE t ADD COLUMN y INTEGER NOT NULL DEFAULT 0;\n",
        encoding="utf-8",
    )
    assert apply_migrations(db_path, mig) == ["0001_add"]
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM schema_migrations WHERE version='0001_add'")
        conn.commit()
    finally:
        conn.close()
    newly = apply_migrations(db_path, mig)
    assert newly == ["0001_add"]
    conn = _connect(db_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(t)")}
        versions = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()
    assert "y" in cols
    assert "0001_add" in versions


def test_migrate_retries_0016_when_column_exists_without_version(tmp_path):
    d = Database(tmp_path / "p.db", tmp_path / "c.db")
    first = migrate(d)
    assert "0016_can_see_company_views" in first["precious"]
    conn = _connect(d.precious_path)
    try:
        conn.execute(
            "DELETE FROM schema_migrations WHERE version='0016_can_see_company_views'"
        )
        conn.commit()
    finally:
        conn.close()
    second = migrate(d)
    assert "0016_can_see_company_views" in second["precious"]
    conn = _connect(d.precious_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        versions = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    finally:
        conn.close()
    assert "can_see_company_views" in cols
    assert "0016_can_see_company_views" in versions


def test_migrate_repairs_missing_company_views_column(tmp_path):
    d = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(d)
    conn = _connect(d.precious_path)
    try:
        try:
            conn.execute("ALTER TABLE users DROP COLUMN can_see_company_views")
            conn.commit()
        except sqlite3.OperationalError as exc:
            pytest.skip(str(exc))
    finally:
        conn.close()
    migrate(d)
    conn = _connect(d.precious_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    finally:
        conn.close()
    assert "can_see_company_views" in cols
    u = UserRepository(d).upsert("dev@x.com", role="developer")
    assert u.can_see_company_views is True


def test_parallel_ensure_company_views_column_does_not_raise(tmp_path):
    from web.data.migrate import _ensure_users_company_views_column

    d = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(d)
    conn = _connect(d.precious_path)
    try:
        try:
            conn.execute("ALTER TABLE users DROP COLUMN can_see_company_views")
            conn.commit()
        except sqlite3.OperationalError as exc:
            pytest.skip(str(exc))
    finally:
        conn.close()
    errors: list[Exception] = []
    barrier = threading.Barrier(4)

    def boot():
        try:
            barrier.wait()
            _ensure_users_company_views_column(d.precious_path)
        except Exception as exc:  # noqa: BLE001 - the test asserts on these
            errors.append(exc)

    threads = [threading.Thread(target=boot) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    conn = _connect(d.precious_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    finally:
        conn.close()
    assert "can_see_company_views" in cols
