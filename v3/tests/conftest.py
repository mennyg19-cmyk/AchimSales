"""Tests must not make real outbound TCP. Mock Graph/HTTP instead."""

from __future__ import annotations

import socket

import pytest

_LOCAL = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def _block_outbound_network(monkeypatch):
    real = socket.create_connection

    def guarded(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if str(host) not in _LOCAL and not str(host).startswith("127."):
            raise RuntimeError(f"outbound network blocked in tests: {address}")
        return real(address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", guarded)
    # Weekday calendar so schedule tests run. Fail-closed / Shabbos tests
    # patch _fetch_items themselves.
    monkeypatch.setattr("web.scheduling.sabbath._fetch_items", lambda now: [])
