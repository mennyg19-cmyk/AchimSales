"""In-process helpers plus a separate worker process on the B1.

- JobWorker: tests drain inline; production ``run_forever`` claims one job and
  runs it in a killable child (``python -m web.jobs.child``).
- Scheduler: APScheduler wrapper, started only in the worker process.
"""
