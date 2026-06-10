"""Tests for asyncio client-disconnect handling."""

from __future__ import annotations

import asyncio

from webapp.asyncio_compat import _is_client_abort, install_client_disconnect_exception_handler


def test_is_client_abort_connection_reset():
    assert _is_client_abort(ConnectionResetError())


def test_is_client_abort_winerror_10054():
    err = OSError()
    err.winerror = 10054  # type: ignore[attr-defined]
    assert _is_client_abort(err)


def test_is_client_abort_ignores_other_errors():
    assert not _is_client_abort(ValueError("nope"))


def test_install_handler_swallows_client_abort():
    loop = asyncio.new_event_loop()
    seen: list[dict] = []

    def capture(_loop: asyncio.AbstractEventLoop, context: dict) -> None:
        seen.append(context)

    loop.set_exception_handler(capture)
    install_client_disconnect_exception_handler(loop)
    loop.call_exception_handler(
        {"exception": ConnectionResetError(10054, "closed")}
    )
    assert seen == []
    loop.call_exception_handler({"exception": RuntimeError("real")})
    assert len(seen) == 1
    loop.close()
