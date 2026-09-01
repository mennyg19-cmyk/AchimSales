"""HTTP helper: turn queue backpressure into a 503."""

from __future__ import annotations

from flask import abort

from web.data.repositories.jobs import QueueAdmissionError


def enqueue_or_503(fn):
    try:
        return fn()
    except QueueAdmissionError as exc:
        abort(503, description=str(exc))
