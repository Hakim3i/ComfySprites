"""Asyncio compatibility helpers (mainly Windows + streaming clients)."""

from __future__ import annotations

import asyncio

# Browser closed a connection mid-response (video range seek, tab change, new src).
_CLIENT_ABORT_ERRORS = (ConnectionResetError, BrokenPipeError)


def _is_client_abort(exc: BaseException | None) -> bool:
    if exc is None:
        return False
    if isinstance(exc, _CLIENT_ABORT_ERRORS):
        return True
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10054:
        return True
    return False


def install_client_disconnect_exception_handler(
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """Ignore asyncio callback noise when a client aborts a partial download.

    Uvicorn/Starlette ``StaticFiles`` returns ``206 Partial Content`` for
    ``<video>`` range requests. Browsers often close the socket early when
    seeking or swapping ``src``, which on Windows ProactorEventLoop surfaces as::

        ConnectionResetError: [WinError 10054] ...
        Exception in callback _ProactorBasePipeTransport._call_connection_lost

    The transfer already succeeded (see 206/304 in access logs); this handler
    only suppresses the spurious traceback.
    """
    loop = loop or asyncio.get_running_loop()
    previous = loop.get_exception_handler()

    def handler(inner_loop: asyncio.AbstractEventLoop, context: dict) -> None:
        if _is_client_abort(context.get("exception")):
            return
        if previous is not None:
            previous(inner_loop, context)
        else:
            inner_loop.default_exception_handler(context)

    loop.set_exception_handler(handler)
