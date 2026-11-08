"""Chatbot unit tests must never reach the network: block non-loopback sockets.

Any LLM/HTTP call a test forgot to patch then fails fast with an OSError, like
a real network outage, instead of silently calling a provider.
"""

from __future__ import annotations

import socket

import pytest

_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}  # noqa: S104


def _is_loopback(address: object) -> bool:
    if isinstance(address, tuple) and address:
        return str(address[0]) in _LOOPBACK
    return isinstance(address, str)  # AF_UNIX path


@pytest.fixture(autouse=True)
def _block_outbound_network(monkeypatch):
    real_connect = socket.socket.connect
    real_create = socket.create_connection

    def guarded_connect(self, address):
        if not _is_loopback(address):
            raise OSError(f"network blocked in chatbot tests: {address!r}")
        return real_connect(self, address)

    def guarded_create(address, *args, **kwargs):
        if not _is_loopback(address):
            raise OSError(f"network blocked in chatbot tests: {address!r}")
        return real_create(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create)
    yield
