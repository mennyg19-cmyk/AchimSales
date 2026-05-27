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
        else:
            log.error("bootstrap: salvage failed; starting with empty DB. "
                      "Run /test/diag/db/repair after boot to retry.")
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

    Returns True on success. Writes go to ``<persistent>.snap.tmp``
    first and only get renamed into place after the backup completes,
    so a crashing snapshot can't leave a torn file behind. SMB rename
    is reasonably atomic on Azure Files.
    """
    if APP_DB_PERSISTENT_PATH is None:
        return False
    if not APP_DB_PATH.exists():
        return False

    APP_DB_PERSISTENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = APP_DB_PERSISTENT_PATH.with_name(APP_DB_PERSISTENT_PATH.name + ".snap.tmp")

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
        # Atomic-ish on SMB. On rare failures we leave .snap.tmp on
        # disk; the next snapshot pass overwrites it.
        tmp_dst.replace(APP_DB_PERSISTENT_PATH)
        return True
    except Exception:
        log.exception("snapshot: backup to %s failed", APP_DB_PERSISTENT_PATH)
        try:
            tmp_dst.unlink(missing_ok=True)
        except Exception:
            pass
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


def request_snapshot_soon() -> None:
    """Wake the snapshot loop so the next pass runs immediately.

    Call from any path that writes "can't be reconstructed from API"
    data -- app_users updates, app_salesmen edits, manager
    assignments, etc. Cheap (just sets an Event) so it's safe to
    sprinkle liberally. No-op when the loop hasn't started (e.g.
    local dev).
    """
    _snapshot_wakeup.set()


def start_snapshot_loop() -> None:
    """Spawn the background snapshot thread. Idempotent."""
    global _started
    with _lock:
        if _started:
            return
        if APP_DB_PERSISTENT_PATH is None:
            log.info("db_sync: no persistent path; snapshot loop skipped")
            return
        t = threading.Thread(target=_loop, name="db_sync", daemon=True)
        t.start()
        # Best-effort final flush on graceful shutdown. Container
        # SIGKILL won't get here, but normal restarts will.
        atexit.register(snapshot_to_persistent)
        _started = True
        log.info("db_sync: snapshot loop started")
