from collections.abc import Callable
from typing import TypeVar

from flask import abort

from web.data.repositories.jobs import QueueAdmissionError

T = TypeVar("T")


def enqueue_or_503(enqueue: Callable[[], T]) -> T:
    try:
        return enqueue()
    except QueueAdmissionError as exc:
        abort(503, description=str(exc))
