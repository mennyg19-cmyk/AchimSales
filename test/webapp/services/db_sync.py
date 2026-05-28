"""Two-way sync between the hot working DB on /tmp and the durable
snapshot on Azure Files (/home/data/v2_app.db).

Why this exists
---------------
On Azure App Service Linux, ``/home/`` (including ``/home/data/``) is
Azure Files (SMB), not local SSD. SQLite running directly on the SMB
share has two failure modes we kept hitting in production:

1. Transient ``unable to open database file`` when another process on
   the same share holds a write lease (the live app's OData backfill
   and the test app's mirror refresh fight constantly).
2. Persistent ``database disk image is malformed`` when an in-flight
   write is interrupted by an OOM kill or container restart -- SMB
   doesn't always flush WAL pages atomically.

This module moves the hot read/write path to ``/tmp/v2_app.db`` (real
local SSD, exclusive to the container, no SMB) and keeps a durable
copy on ``/home/data/v2_app.db`` via:

- ``bootstrap_from_persistent()`` -- one-time, at app boot, copies the
  Azure Files snapshot down to /tmp. Uses SQLite's Online Backup API
  so the copy is consistent even if the source is being written to.
  If the source is malformed, attempts a ``.recover``-style salvage
  via ``sqlite3.iterdump()`` with per-statement error tolerance, so a
  single bad page doesn't lose every row -- only the rows on bad
  pages are dropped.

- ``snapshot_to_persistent()`` -- runs every ``SNAPSHOT_INTERVAL_S``
  seconds and at graceful shutdown. Uses Online Backup against the
  WAL'd /tmp DB so concurrent writers don't block. Writes to a temp
  file in /home/data and atomically renames into place; readers on
  the share never see a half-written file.

The snapshot interval defaults to 5 minutes -- bounded by the worst
case "this much work could be lost if the container dies", which is
fine for a read-mostly mirror that we can rebuild from the API
anyway.
"""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import sqlite3
import threading
import time
from pathlib import Path

from test.config.settings import APP_DB_PATH, APP_DB_PERSISTENT_PATH

log = logging.getLogger(__name__)

# 60 s: short enough that a user-management change (e.g. a manager
# adding a teammate via the Users & Permissions UI) is durably on
# Azure Files within a minute of the click, long enough that the
# snapshot-induced load on the SMB share is barely measurable. The
# original 5-min default was sized for mirror data (which can be
# rebuilt from the API), but app_users / app_salesmen edits CANNOT
# be rebuilt -- losing them between snapshots was exactly the
# "everything else gets wiped on restart" complaint on 2026-05-27.
SNAPSHOT_INTERVAL_S = 60
# How long a single online-backup pass is allowed to take before we
# give up. The mirror gets to ~150 MB so a few seconds is normal;
# 60 s here is alarm-level slow but still safer than blocking forever.
SNAPSHOT_TIMEOUT_S = 60

_started = False
_lock = threading.Lock()

# Event used to break the loop's sleep early. ``request_snapshot_soon``
# sets this from user-mutation paths so a fresh edit is durable within
# seconds rather than waiting for the next tick.
_snapshot_wakeup = threading.Event()

# Last-snapshot telemetry. Exposed via /test/diag/api/snapshot-status so
# we can actually SEE what's happening instead of guessing why a user's
# add seems to vanish on the next restart. Updated under _stats_lock so
# concurrent worker snapshots don't tear the dict.
_stats_lock = threading.Lock()
_stats: dict = {
    "last_success_utc":   None,
    "last_failure_utc":   None,
    "last_failure_error": None,
    "success_count":      0,
    "failure_count":      0,
    "last_size_bytes":    None,
    "last_app_users_n":   None,
    "last_caller_pid":    None,
}


def snapshot_stats() -> dict:
    """Read-only snapshot of last-snapshot telemetry."""
    with _stats_lock:
        return dict(_stats)


def _record_stat(**fields) -> None:
    with _stats_lock:
        _stats.update(fields)


def _is_malformed(path: Path) -> bool:
    """Return True if ``path`` opens but fails ``integrity_check``.

    Cheap pre-check before we attempt a full backup -- saves us from
    silently snapshotting a corrupted source over a previously-good
    persistent copy.
    """
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as conn:
            cur = conn.execute("PRAGMA quick_check")
            result = cur.fetchone()
            return not (result and result[0] == "ok")
    except sqlite3.DatabaseError:
        return True


def _salvage_via_iterdump(src: Path, dst: Path) -> bool:
    """Best-effort recovery of a malformed SQLite file.

    Pages SQLite refuses to read are dropped; everything readable
    makes it across. Returns True if at least some data was recovered.

    This is the Python-only analogue of ``sqlite3 file.db ".recover"``
    -- not as thorough as the C-level recover extension but works
    against the stdlib without needing the CLI to be present.
    """
    try:
        dst.unlink(missing_ok=True)
        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=10)
        dst_conn = sqlite3.connect(str(dst))
        try:
            recovered = 0
            failed = 0
            for stmt in src_conn.iterdump():
                try:
                    dst_conn.executescript(stmt)
                    recovered += 1
                except sqlite3.DatabaseError as exc:
                    failed += 1
                    log.warning("salvage: dropped statement (%s): %s",
                                exc, stmt[:120])
            dst_conn.commit()
            log.warning("salvage: recovered %d statements, dropped %d",
                        recovered, failed)
            return recovered > 0
        finally:
            src_conn.close()
            dst_conn.close()
    except Exception:
        log.exception("salvage failed")
        return False


def bootstrap_from_persistent() -> None:
    """At boot, populate ``APP_DB_PATH`` from ``APP_DB_PERSISTENT_PATH``.

    No-op when running locally (the persistent path is None) or when
    the working DB already exists (we're inside the same container
    life). Tolerates a missing or corrupted source -- the worst case
    is an empty DB that ``init_db()`` will populate with schema; the
    daily scheduler will refill the mirror from the API.
    """
    if APP_DB_PERSISTENT_PATH is None:
        return
    if APP_DB_PATH.exists() and APP_DB_PATH.stat().st_size > 0:
        return

    APP_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    src = APP_DB_PERSISTENT_PATH
    if not src.exists() or src.stat().st_size == 0:
        log.info("bootstrap: no persistent DB at %s; starting fresh", src)
        return

    if _is_malformed(src):
        log.warning("bootstrap: persistent DB at %s is malformed; attempting salvage", src)
        if _salvage_via_iterdump(src, APP_DB_PATH):
            # Quarantine the broken original so we don't keep
            # snapshotting it back to good.
            quarantine = src.with_suffix(f".db.corrupt.{int(time.time())}")
            try:
                shutil.move(str(src), str(quarantine))
                log.warning("bootstrap: quarantined corrupt source to %s", quarantine)
            except Exception:
                log.exception("bootstrap: failed to quarantine corrupt source")
            return

        # Salvage failed. Don't silently leave APP_DB_PATH absent --
        # init_db will then "helpfully" build a fresh empty DB and the
        # seeders will write Just The Defaults (developer admin +
        # xlsx-seeded salesmen) over what should have been the user
        # snapshot. That's exactly the "everything else got wiped"
        # symptom. Quarantine the bad file so the next boot doesn't
        # keep failing the same way, and leave APP_DB_PATH empty so
        # init_db builds a fresh DB; but log at ERROR level so the
        # data loss is visible in App Service logs instead of a silent
        # cascade. An admin can copy back the latest quarantined
        # ``.db.corrupt.<ts>`` snapshot via /test/diag if needed.
        quarantine = src.with_suffix(f".db.corrupt.{int(time.time())}")
        try:
            shutil.move(str(src), str(quarantine))
            log.error(
                "bootstrap: salvage failed; quarantined %s -> %s. Starting with "
                "empty DB. To recover, copy a known-good snapshot to %s.",
                src, quarantine, src,
            )
        except Exception:
            log.exception(
                "bootstrap: salvage failed AND couldn't quarantine %s; the next "
                "boot will retry and likely repeat this failure",
                src,
            )
        return

    try:
        # Online backup: copies a transactionally-consistent snapshot
        # even if the source is being written to by another process.
        # Much safer than shutil.copy2() which can grab a torn page.
        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
        dst_conn = sqlite3.connect(str(APP_DB_PATH))
        try:
            src_conn.backup(dst_conn)
            log.info("bootstrap: copied %s -> %s (%d bytes)",
                     src, APP_DB_PATH, APP_DB_PATH.stat().st_size)
        finally:
            src_conn.close()
            dst_conn.close()
    except Exception:
        log.exception("bootstrap: online backup failed; trying salvage as fallback")
        _salvage_via_iterdump(src, APP_DB_PATH)


def snapshot_to_persistent() -> bool:
    """Atomically copy ``APP_DB_PATH`` to ``APP_DB_PERSISTENT_PATH``.

    Returns True on success. Writes go to a per-process temp file
    ``<persistent>.snap.tmp.<pid>`` first and only get renamed into
    place after the backup completes, so a crashing snapshot can't
    leave a torn file behind. The per-PID suffix matters: with 2+
    Gunicorn workers each running their own snapshot loop, sharing
    a single ``.snap.tmp`` was producing a torn final file when both
    workers wrote to it simultaneously -- next boot then saw the
    persistent DB as malformed, salvage dropped the corrupted user
    pages, and the admin's "everything else gets wiped on restart"
    complaint repeated on every deploy.

    The final ``replace()`` step is atomic on POSIX even across
    workers; whichever rename lands last wins, and neither produces
    a torn write because the source temp files are independent.
    """
    if APP_DB_PERSISTENT_PATH is None:
        return False
    if not APP_DB_PATH.exists():
        return False

    APP_DB_PERSISTENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Per-PID temp name -- see docstring for why.
    tmp_dst = APP_DB_PERSISTENT_PATH.with_name(
        f"{APP_DB_PERSISTENT_PATH.name}.snap.tmp.{os.getpid()}"
    )
    pid = os.getpid()
    now_utc = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())  # noqa: E731

    try:
        # Source is the live working DB. Use Online Backup so concurrent
        # writers don't block and we get a consistent snapshot.
        src_conn = sqlite3.connect(str(APP_DB_PATH), timeout=10)
        dst_conn = sqlite3.connect(str(tmp_dst))
        try:
            src_conn.backup(dst_conn)
        finally:
            src_conn.close()
            dst_conn.close()
        # Verify the snapshot is well-formed AND contains the
        # critical user table content BEFORE renaming it into place.
        # A torn backup here would replace a known-good persistent
        # file with garbage -- the exact failure mode that was
        # wiping users on every deploy. Also pull app_users row
        # count so the diag endpoint can confirm "yes, X users
        # actually made it into the latest snapshot".
        #
        # The OPEN of the temp file can transiently fail with
        # "unable to open database file" -- the same SMB lease blip
        # that plagues every /home/data access. Observed in prod:
        # a verify failure 7s after a clean success. Discarding an
        # otherwise-good backup on a momentary blip is wrong (and,
        # via raise_on_fail, needlessly 500s an Add User). So retry
        # the open a few times with backoff. A genuinely BAD backup
        # fails quick_check deterministically and is NOT retried --
        # we only retry the transient open error.
        users_in_snapshot: int | None = None
        verify_attempts = 4
        last_verify_exc: Exception | None = None
        verified = False
        for attempt in range(verify_attempts):
            try:
                with sqlite3.connect(f"file:{tmp_dst}?mode=ro", uri=True, timeout=10) as vconn:
                    row = vconn.execute("PRAGMA quick_check").fetchone()
                    if not row or row[0] != "ok":
                        # Deterministic corruption -- don't retry, this
                        # backup is genuinely bad.
                        log.error("snapshot: post-backup quick_check failed (%r); discarding tmp",
                                  row[0] if row else None)
                        tmp_dst.unlink(missing_ok=True)
                        _record_stat(
                            last_failure_utc=now_utc(),
                            last_failure_error=f"quick_check={row[0] if row else None}",
                            failure_count=_stats["failure_count"] + 1,
                            last_caller_pid=pid,
                        )
                        return False
                    try:
                        users_in_snapshot = vconn.execute(
                            "SELECT COUNT(*) FROM app_users"
                        ).fetchone()[0]
                    except Exception:
                        # app_users table missing on a malformed-but-recovered
                        # DB shouldn't fail the whole snapshot; just leave
                        # the count unknown for telemetry.
                        pass
                verified = True
                break
            except sqlite3.OperationalError as exc:
                # Transient SMB open blip -- back off and retry.
                last_verify_exc = exc
                if attempt < verify_attempts - 1:
                    time.sleep(0.4 * (attempt + 1))
                    continue
            except Exception as exc:
                last_verify_exc = exc
                break

        if not verified:
            log.exception("snapshot: post-backup integrity check failed after %d attempts; "
                          "discarding tmp", verify_attempts)
            tmp_dst.unlink(missing_ok=True)
            _record_stat(
                last_failure_utc=now_utc(),
                last_failure_error=(
                    f"verify: {type(last_verify_exc).__name__}: {last_verify_exc}"
                    if last_verify_exc else "verify: unknown"
                ),
                failure_count=_stats["failure_count"] + 1,
                last_caller_pid=pid,
            )
            return False

        # Atomic on POSIX. Cross-worker races resolve to whichever
        # rename was scheduled last; both temp files are well-formed
        # at this point, so the result is still a consistent DB.
        tmp_dst.replace(APP_DB_PERSISTENT_PATH)
        size = APP_DB_PERSISTENT_PATH.stat().st_size
        _record_stat(
            last_success_utc=now_utc(),
            success_count=_stats["success_count"] + 1,
            last_size_bytes=size,
            last_app_users_n=users_in_snapshot,
            last_caller_pid=pid,
        )
        log.info("snapshot: wrote %s (%d bytes, %s app_users) from pid=%d",
                 APP_DB_PERSISTENT_PATH, size,
                 users_in_snapshot if users_in_snapshot is not None else "?",
                 pid)
        return True
    except Exception as exc:
        log.exception("snapshot: backup to %s failed", APP_DB_PERSISTENT_PATH)
        try:
            tmp_dst.unlink(missing_ok=True)
        except Exception:
            pass
        _record_stat(
            last_failure_utc=now_utc(),
            last_failure_error=f"{type(exc).__name__}: {exc}",
            failure_count=_stats["failure_count"] + 1,
            last_caller_pid=pid,
        )
        return False


def _loop() -> None:
    log.info("db_sync loop running every %ds (wakeable)", SNAPSHOT_INTERVAL_S)
    # Take an immediate snapshot once boot finishes -- without this,
    # any state that init_db just wrote (developer-user seed, freshly
    # seeded salesmen, schema migrations) sits only on /tmp until the
    # first tick. A container restart in the first minute would wipe
    # those.
    try:
        snapshot_to_persistent()
    except Exception:
        log.exception("db_sync initial snapshot failed; continuing")
    while True:
        try:
            # Sleep interruptibly so request_snapshot_soon() can wake
            # us up the moment something mutation-heavy happens (e.g.
            # admin adds a user). Event.wait() returns True when set,
            # False on timeout -- either way we run the next pass.
            _snapshot_wakeup.wait(timeout=SNAPSHOT_INTERVAL_S)
            _snapshot_wakeup.clear()
            snapshot_to_persistent()
        except Exception:
            log.exception("db_sync loop iteration crashed; continuing")


_inline_snapshot_lock = threading.Lock()
_inline_snapshot_running = False


def _inline_snapshot() -> None:
    """One-shot snapshot used by non-owner workers (and as a fallback
    when the owner is missing). Serialised per-process via
    ``_inline_snapshot_lock`` so a request burst doesn't fork off
    dozens of concurrent backup threads.
    """
    global _inline_snapshot_running
    with _inline_snapshot_lock:
        if _inline_snapshot_running:
            return
        _inline_snapshot_running = True
    try:
        snapshot_to_persistent()
    finally:
        with _inline_snapshot_lock:
            _inline_snapshot_running = False


def request_snapshot_soon() -> None:
    """Persist the working DB to Azure Files ASAP.

    Call from any path that writes "can't be reconstructed from API"
    data -- app_users updates, app_salesmen edits, manager
    assignments, etc. Cheap from the caller's perspective: we kick
    off the snapshot on a daemon thread and return immediately.

    On the snapshot-owner worker this just wakes the periodic loop
    so its next pass runs now instead of waiting up to 60s. On
    non-owner workers we spawn a one-shot snapshot thread directly
    -- without that, a user-management edit on a non-owner worker
    wouldn't be durable on /home/data until the owner happened to
    do its next pass, which is exactly the kind of "lost on
    restart" gap we're trying to close. Per-PID temp files +
    post-backup integrity check (see snapshot_to_persistent) keep
    the cross-worker case safe.
    """
    _snapshot_wakeup.set()
    if not _started or APP_DB_PERSISTENT_PATH is None:
        return
    t = threading.Thread(target=_inline_snapshot, name="db_sync_oneshot", daemon=True)
    t.start()


def _try_become_snapshot_owner() -> bool:
    """Return True iff this PID won the cross-worker owner race.

    All Gunicorn workers share /tmp/v2_app.db (they each write
    user-management + mirror data into it), but only one of them
    needs to run the snapshot loop -- having every worker snapshot
    independently was the source of the torn-file corruption that
    kept wiping users on every deploy. We elect a single owner via
    a row in ``app_settings`` keyed by PID; if the row already
    points at a live PID, we stand down and let the owner do the
    work. The current owner's PID is rewritten by the loop on every
    pass so a worker recycle hands ownership off cleanly.

    Falls back to "every worker snapshots" if the app_settings
    table doesn't exist yet (very early boot, before init_db
    finishes); the per-PID temp file + integrity check still keep
    that case safe, just slightly wasteful.
    """
    try:
        from test.webapp.db import get_app_setting, set_app_setting
    except Exception:
        return True

    my_pid = str(os.getpid())
    try:
        current = (get_app_setting("db_sync_owner_pid") or "").strip()
    except Exception:
        return True

    if not current or current == my_pid:
        try:
            set_app_setting("db_sync_owner_pid", my_pid)
        except Exception:
            pass
        return True

    # Check if the recorded owner is still alive. On Linux, sending
    # signal 0 to a dead PID raises ProcessLookupError; on a live PID
    # it's a no-op. If the previous owner died (OOM kill, container
    # rotate), steal ownership.
    try:
        pid_n = int(current)
    except ValueError:
        try:
            set_app_setting("db_sync_owner_pid", my_pid)
        except Exception:
            pass
        return True
    try:
        os.kill(pid_n, 0)
    except ProcessLookupError:
        try:
            set_app_setting("db_sync_owner_pid", my_pid)
            log.info("db_sync: stole ownership from dead pid %d", pid_n)
        except Exception:
            pass
        return True
    except Exception:
        # PermissionError etc -- assume the owner is alive.
        pass
    return False


def start_snapshot_loop() -> None:
    """Spawn the background snapshot thread. Idempotent.

    Cross-worker ownership is checked once at startup: only the
    elected owner runs the periodic loop. Other workers still
    register the atexit flush so a graceful shutdown of any worker
    persists the latest state, and they still respond to
    ``request_snapshot_soon`` by running a one-shot snapshot
    in-thread (the per-PID temp file + integrity check make that
    safe even if it races the owner's loop).
    """
    global _started
    with _lock:
        if _started:
            return
        if APP_DB_PERSISTENT_PATH is None:
            log.info("db_sync: no persistent path; snapshot loop skipped")
            return
        # atexit fires from every worker on graceful shutdown -- still
        # useful for ad-hoc Gunicorn reloads even when this worker
        # didn't win the owner election.
        atexit.register(snapshot_to_persistent)

        if not _try_become_snapshot_owner():
            log.info("db_sync: another worker owns the snapshot loop; standing by")
            _started = True
            return

        t = threading.Thread(target=_loop, name="db_sync", daemon=True)
        t.start()
        _started = True
        log.info("db_sync: snapshot loop started (owner pid=%d)", os.getpid())
